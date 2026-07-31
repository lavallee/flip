"""Source capture: fetcher routing, custody, provenance, entity pages (SPEC §5).

`add_source` is the write path for `flip add-source`: classify the target,
allocate a kind-prefixed id, capture bytes into sources/raw/ (builtin copy for
local files, a configured [fetchers] command for everything else via the
integrations layer), hash every captured file into sources/_provenance.jsonl
(append-only), and open a references/<slug>.md entity page graded "?" — the
canonical record of the source (SPEC §5.3). `grade_source` is the write path
for `flip grade`: record the judgment keys on an existing page, round-tripping
everything else on it (frontmatter flip doesn't own and the prose body survive,
SPEC §6.6).

Fetcher command templates and the capture runner live in `integrations` (SPEC
§15). A fetcher may hand back an optional neutral return envelope; when present,
its title/canonical_url flow onto the page and its strategy/retrieved_at/status/
backend_ref into provenance. Independence/freshness *hints* are recorded as a
page note only — grading stays a judgment made after reading, never auto-set.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from . import integrations, manifest, pages
from .util import (
    append_jsonl,
    detect_actor,
    read_jsonl,
    require_notebook_root,
    sha256_file,
    utc_now,
)

GRADES = ("A", "B", "C", "D", "?")
INDEPENDENCE = ("independent", "corroborated", "self-reported", "derivative")
FRESHNESS = ("fresh", "dated")

# Pre-0.8 `independence` vocabulary, kept recognizable on purpose (0.16).
#
# The axis changed, not the spelling: pre-0.8 `independence` encoded *custody*
# ("we hold the original bytes, not a copy"), 0.8 encodes *epistemics* ("is
# this evidence independent of its own subject"). An exact-commit copy of a
# project's own README is original custody AND self-reported evidence, so no
# mechanical translation is honest. A page still carrying one of these values
# is therefore a MISSING judgment, not a weak one — `judged` says no,
# `derive_grade` returns "?", and doctor names it.
PRE_08_INDEPENDENCE = ("original", "republisher", "self-interested")

# The support tuple (SPEC §5.4, design D-A): evidence *description*, authored
# as the act of judgment; the letter grade is derived from it, never stored
# as an opinion of its own. `independence` is the tuple's spine and keeps its
# own top-level frontmatter key (continuity with pre-0.8 pages).
BASES = (
    "official-record",
    "platform-data",
    "measured",
    "survey",
    "panel",
    "single-operator",
    "synthesis",
    "spoken-management-remarks",
)
_STRONG_BASES = ("official-record", "platform-data", "measured")

# Capture methods (SPEC §5.1): HOW a capture got its bytes, in escalation
# order. The provenance ledger already records the *actor* — `tool` and
# `tool_version` — so `strategy` is where the METHOD belongs.
#
# Recording the method rather than the tool is what makes two notebooks
# comparable when they were built on different deployments: `archive-replay`
# means the same thing whoever implemented it, while a tool name is local
# trivia (and, for a private tool, unpublishable). It is also the honest
# fidelity signal — a capture that stopped at `http-get` with 4KB and one that
# reached `self-contained-archive` are not the same evidence, and until now
# they produced identical pages.
#
# The order is the ladder an acquisition should climb before giving up: a
# single 403 is the START of the work, not the end of it.
CAPTURE_METHODS = (
    "copy",                    # builtin: a local file copied verbatim
    "http-get",                # a plain GET of the live URL
    "http-alt-representation", # canonical/AMP/print/embed variant of the same URL
    "archive-replay",          # a third-party web archive served the bytes
    "publisher-api",           # a publisher/registry API (Crossref, Unpaywall, arXiv…)
    "media-extract",           # a media/transcript extractor
    "browser-render",          # a headless browser executed the page
    "browser-session",         # browser render carrying an authenticated session
    "self-contained-archive",  # assets inlined into one standalone file
    "human-in-loop",           # a person saved it and handed flip the file
)

# Methods that produce a page whose linked assets are NOT captured — the bytes
# are the document's text, not a faithful copy of what a reader saw.
_TEXT_ONLY_METHODS = ("http-get", "http-alt-representation", "archive-replay")

# Provenance terminal states (SPEC §5.5, design D-B): where the chain-walk
# behind this source ended. Optional; doctor gates done/published on OPEN.
PROVENANCE_STATES = (
    "PRIMARY-REACHED",
    "PRIMARY-GATED",
    "PRIMARY-LOST",
    "PRIMARY-NEVER-PUBLISHED",
    "PRIMARY-EXISTS-PRIVATE",
    "PRIMARY-OPEN",
)


def _support(fm: dict) -> dict:
    value = fm.get("support")
    return value if isinstance(value, dict) else {}


def capture_fidelity(event: dict) -> str:
    """What a capture event actually achieved — DERIVED from the ledger row,
    never stored (the same discipline as `derive_grade`).

    `faithful`   — assets inlined, a rendered page, or a verbatim local copy.
    `text-only`  — the document's text, but linked assets were not captured.
    `thin`       — succeeded and brought back almost nothing: a consent wall,
                   a JS shell, an error page served with status 200. This is
                   the dangerous one, because custody, a sha256 and a
                   provenance row all look identical to a real capture.
    `unknown`    — no method recorded, or one outside the vocabulary.

    Callers pass one provenance event ({strategy, bytes, mime, …}).
    """
    method = str(event.get("strategy") or "")
    if method not in CAPTURE_METHODS:
        return "unknown"
    size = event.get("bytes")
    mime = str(event.get("mime") or "")
    # A markup response carrying almost no payload didn't capture the document,
    # whatever the status line said. Non-markup (PDF, CSV) is legitimately small.
    markup = "html" in mime or "xml" in mime or (not mime and method != "copy")
    if isinstance(size, int) and markup and size < 2048:
        return "thin"
    return "text-only" if method in _TEXT_ONLY_METHODS else "faithful"


def unmigrated(fm: dict) -> bool:
    """True when a page still carries pre-0.8 `independence` vocabulary.

    See PRE_08_INDEPENDENCE: the value describes custody, not epistemics, so
    flip cannot read it as a judgment. Callers that show a corroboration count
    name these sources alongside it — a wrong count is worse than a missing
    one, because only the missing one prompts a look.
    """
    return str(fm.get("independence") or "") in PRE_08_INDEPENDENCE


def judged(fm: dict) -> bool:
    """True when a judgment flip can actually read is recorded: `independence`
    in the 0.8 vocabulary (the tuple's spine), or a migration seed standing in
    for a pre-0.8 authored letter.

    Out-of-vocabulary `independence` is NOT a judgment. Until 0.16 any truthy
    value counted as one, so a page left on pre-0.8 vocabulary was "judged",
    displayed a confident A, and corroborated nothing — three surfaces
    disagreeing in silence.
    """
    independence = str(fm.get("independence") or "")
    if independence:
        return independence in INDEPENDENCE
    return _support(fm).get("seeded") == "legacy-grade"


def derive_grade(fm: dict) -> str:
    """The letter digest of a source's support tuple — a summary, never a
    store (design D-A). Deterministic and recomputable; doctor flags drift.

    A: independent + strong basis (official-record/platform-data/measured),
       with `base_defined` not recorded false.
    B: independent/corroborated with basis and method recorded.
    C: every other recorded judgment (self-reported, synthesis-grade bases,
       undefined base on a quantitative source).
    D: derivative — a lead, never provenance.
    ?: unjudged — including a page still carrying pre-0.8 `independence`
       vocabulary, which is a missing judgment rather than a weak one. A
       `support.seeded: legacy-grade` marker on an otherwise-current page
       returns the stored pre-0.8 letter until a real grading replaces it.
    """
    if not judged(fm):
        return "?"
    support = _support(fm)
    if support.get("seeded") == "legacy-grade":
        stored = str(fm.get("grade") or "?")
        return stored if stored in GRADES else "?"
    independence = str(fm.get("independence") or "")
    if independence == "derivative":
        return "D"
    if support.get("base_defined") is False:
        return "C"
    basis = str(support.get("basis") or "")
    if independence == "independent" and basis in _STRONG_BASES:
        return "A"
    if independence in ("independent", "corroborated") and basis and support.get("method"):
        return "B"
    return "C"


# Which support-tuple fields move the letter and which are documentation.
# Only three fields decide the grade, plus `method` which alone gates B;
# `n`/`vintage`/`freshness` never move it. That was discoverable only by
# reading derive_grade, so `flip grade --explain` prints it.
GRADE_INPUTS = ("independence", "basis", "base_defined", "method")
GRADE_DOCUMENTATION = ("n", "vintage", "freshness")


def explain_grade(fm: dict) -> dict:
    """Why this source derives the letter it does (`flip grade --explain`).

    Returns {grade, reason, next, inputs, documentation}: `inputs` are the
    four tuple fields that move the letter, `documentation` the three that
    never do, `reason` the rule that fired, and `next` the shortest honest
    path to a higher letter.
    """
    support = _support(fm)
    independence = str(fm.get("independence") or "")
    basis = str(support.get("basis") or "")
    grade = derive_grade(fm)
    strong = ", ".join(_STRONG_BASES)
    inputs = {
        "independence": independence or None,
        "basis": basis or None,
        "base_defined": support.get("base_defined"),
        "method": support.get("method") or None,
    }
    documentation = {
        "n": support.get("n") or None,
        "vintage": support.get("vintage") or None,
        "freshness": fm.get("freshness") or None,
    }

    if unmigrated(fm):
        reason = (
            f"independence '{independence}' is pre-0.8 vocabulary — it encoded custody, "
            "not epistemics, so it is a missing judgment rather than a weak one; this "
            "source corroborates nothing until re-judged"
        )
        nxt = f"re-judge it: --independence {'|'.join(INDEPENDENCE)}"
    elif not judged(fm):
        reason = (
            "no judgment recorded — capture is custody, not judgment, and an unjudged "
            "source counts toward nothing"
        )
        nxt = "judge it after reading: --independence … --basis …"
    elif support.get("seeded") == "legacy-grade":
        reason = (
            f"grade {grade} is a migration seed carrying a pre-0.8 authored letter, "
            "not a derivation from the support tuple"
        )
        nxt = "replace the seed with a real judgment: --independence … --basis …"
    elif independence == "derivative":
        reason = "independence 'derivative' — a lead, never provenance"
        nxt = "D is terminal for a republisher; capture the source it republishes instead"
    elif support.get("base_defined") is False:
        reason = (
            "base recorded undefined — the measured quantity itself is unspecified, "
            "which caps the digest at C whatever else the tuple says"
        )
        nxt = "define what is being measured, then re-grade with --base-defined"
    elif grade == "A":
        reason = f"independence 'independent' + strong basis '{basis}', base not undefined"
        nxt = "A is the ceiling"
    elif grade == "B":
        reason = (
            f"independence '{independence}' with basis '{basis}' and a recorded method "
            "(method alone is what gates B)"
        )
        nxt = f"A needs independence 'independent' and a strong basis ({strong})"
    else:
        why = []
        if independence not in ("independent", "corroborated"):
            why.append(f"independence '{independence}' is neither independent nor corroborated")
        if not basis:
            why.append("no basis recorded")
        elif independence == "independent" and basis not in _STRONG_BASES:
            why.append(f"basis '{basis}' is not a strong basis ({strong})")
        if basis and not support.get("method"):
            why.append("no method recorded, and method alone is what gates B")
        reason = "; ".join(why) or "no rule above C matched"
        if independence in ("independent", "corroborated") and basis and not support.get("method"):
            nxt = "B needs --method (one line on how the evidence was produced)"
        elif independence == "independent":
            nxt = f"A needs a strong basis ({strong})"
        else:
            nxt = (
                "C is the honest ceiling for self-reported evidence; corroborate it with "
                "an independent source rather than upgrading this one"
            )
    return {
        "grade": grade,
        "reason": reason,
        "next": nxt,
        "inputs": inputs,
        "documentation": documentation,
    }

# SPEC §9 naming rules: P papers · A articles/web · F files/datasets/documents ·
# T talks/transcripts · S when unkinded/unknown. D is reserved for decisions —
# source ids never use it, so a bare [F3]/[D2] cite is unambiguous.
_ID_PREFIXES = {
    "paper": "P",
    "web": "A",
    "article": "A",
    "file": "F",
    "dataset": "F",
    "document": "F",
    "talk": "T",
    "transcript": "T",
    "social": "A",
}

_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
_ARXIV_RE = re.compile(r"^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
_X_POST_RE = re.compile(
    r"^/(?:i/web/)?(?:[^/]+/)?status(?:es)?/\d+(?:[/?#]|$)", re.IGNORECASE
)
_YT_VIDEO_PATH_RE = re.compile(r"^/(?:shorts|live)/[A-Za-z0-9_-]{11}(?:[/?#]|$)")
_YT_SHORT_HOST_RE = re.compile(r"^/[A-Za-z0-9_-]{11}(?:[/?#]|$)")


def _classify(target: str) -> str:
    """Infer a source kind from the target when the caller didn't name one."""
    if Path(target).expanduser().exists():
        return "file"
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("mobile.")
        if host in {"x.com", "twitter.com"} and _X_POST_RE.match(parts.path):
            return "social"
        # A single YouTube video is a talk (id class T); channels, playlists,
        # and every other YouTube surface stay web — they aren't one
        # capturable spoken record.
        if host in {"youtube.com", "m.youtube.com"} and (
            (parts.path == "/watch" and re.search(r"(?:^|&)v=[A-Za-z0-9_-]{11}(?:&|$)", parts.query))
            or _YT_VIDEO_PATH_RE.match(parts.path)
        ):
            return "talk"
        if host == "youtu.be" and _YT_SHORT_HOST_RE.match(parts.path):
            return "talk"
        return "web"
    if target.lower().startswith("doi:") or _DOI_RE.match(target) or _ARXIV_RE.match(target):
        return "paper"
    raise SystemExit(
        f"can't classify '{target}' (not an existing file, http(s) URL, DOI, or arXiv id) — "
        "pass the kind explicitly, e.g. --kind web|social|paper|file|dataset|talk"
    )


def _capture_copy(root: Path, source_id: str, target: str) -> tuple[list[Path], str]:
    """builtin:copy — copy one local file verbatim into sources/raw/<id><suffix>.

    Returns ([copied path], origin file:// URI).
    """
    src = Path(target).expanduser()
    if src.is_dir():
        raise SystemExit(
            f"'{target}' is a directory — point at a single file, or configure a "
            f"[fetchers] command in {integrations.config_path()} for multi-file captures"
        )
    if not src.is_file():
        raise SystemExit(f"no such file '{target}' — check the path, or pass a URL/DOI instead")
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{source_id}{src.suffix}"
    shutil.copy2(src, dest)
    return [dest], src.resolve().as_uri()


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _title_for(target: str, capture_kind: str) -> str:
    """The human-readable name a capture gets when the fetcher didn't supply one:
    the file basename for copies and host+path for URLs; other targets (DOI,
    arXiv) keep the target string itself."""
    if capture_kind == "copy":
        return Path(target).expanduser().name
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        return f"{parts.netloc}{parts.path}".rstrip("/") or target
    return target


# A fetcher envelope is untrusted input, and flip is the trust boundary. A
# configured fetcher that decodes a binary payload and hands back its first
# bytes as the "title" produced pages named `PK…[Content_Types].xml` (an
# .xlsx) and `%PDF-1.7 1 0 obj` (a PDF) — six needed hand-retitling. Reject a
# title that isn't plausibly text and fall back to the target-derived name.
_BINARY_TITLE_MAGIC = (
    "%PDF", "PK\x03\x04", "\x89PNG", "\x7fELF", "%!PS", "GIF8", "\x1f\x8b", "\xd0\xcf\x11\xe0",
)


def _plausible_title(value: object) -> str | None:
    """A fetcher-supplied title, or None when it looks like binary payload."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith(_BINARY_TITLE_MAGIC):
        return None
    if "[Content_Types].xml" in text:  # OOXML (.xlsx/.docx/.pptx) read as text
        return None
    # A replacement char means bytes were decoded with errors="replace";
    # control bytes mean they weren't text to begin with. Either way: payload.
    if "�" in text or any(ch < " " and ch != "\t" for ch in text):
        return None
    return text


def _hint_note(envelope: dict | None) -> str:
    """Render a fetcher's independence/freshness/status hints as a page note.

    Hints are leads for the grader, never the grade itself (custody discipline):
    they live in the body, not in the judgment frontmatter keys.
    """
    if not envelope:
        return ""
    bits = []
    if envelope.get("independence_hint") in INDEPENDENCE:
        bits.append(f"independence={envelope['independence_hint']}")
    if envelope.get("freshness_hint") in FRESHNESS:
        bits.append(f"freshness={envelope['freshness_hint']}")
    status = envelope.get("status")
    if isinstance(status, str) and status and status != "success":
        bits.append(f"status={status}")
    if not bits:
        return ""
    return (
        "> capture hints (from the fetcher, unverified — judge with `flip grade`): "
        + ", ".join(bits) + "\n"
    )


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def add_source(
    root: Path,
    target: str,
    kind: str | None = None,
    note: str | None = None,
    via: str | None = None,
) -> pages.Page:
    """Capture a source into the notebook; returns its new entity page.

    Routes by kind: "file" (or any kind whose configured fetcher is
    "builtin:copy") copies the file verbatim; everything else runs the
    [fetchers] command resolved from $FLIP_HOME/config.toml (optionally a named
    variant, `--via`). Appends one provenance event per captured file, opens
    references/<slug>.md at grade "?", touches the manifest. Local copies carry
    their origin file:// URI in provenance only; fetched targets also land on
    the page as `resource` (the fetcher's canonical_url when it reports one).
    """
    root = require_notebook_root(root)
    kind = kind or _classify(target)
    source_id = pages.allocate_id(root, _ID_PREFIXES.get(kind, "S"))

    # Route on the TARGET, not only the kind: `--kind dataset ./local.psv` used
    # to demand a [fetchers] command for a file already on disk, while the same
    # path with `--kind file` copied fine. A local path never needs a fetcher.
    local_target = Path(target).expanduser().exists()
    resolved = (
        None if kind == "file" or local_target
        else integrations.resolve("fetchers", kind, via=via)
    )
    envelope: dict | None = None
    if resolved is None or resolved.template == "builtin:copy":
        files, origin = _capture_copy(root, source_id, target)
        tool, tool_version, capture_kind, strategy, url = (
            "builtin:copy", None, "copy", "copy", origin,
        )
    else:
        try:
            run = integrations.run_capture(resolved, root, source_id, target)
        except SystemExit as exc:
            # A failed acquisition is a finding, not just an error (L5): the
            # attempt lands in the ledger — "searched, gone" is distinguishable
            # from "did not look" — then the refusal propagates unchanged.
            append_jsonl(
                root / "sources" / "_provenance.jsonl",
                {
                    "ts": utc_now(),
                    "source_id": source_id,
                    "url": target,
                    "status": "failed",
                    "error": str(exc),
                    "actor": detect_actor(),
                    **({"note": note} if note else {}),
                },
            )
            raise
        files, tool, tool_version = run.files, run.tool, run.tool_version
        capture_kind, strategy, url, envelope = "config", run.strategy, target, run.envelope

    ts = utc_now()
    actor = detect_actor()
    prov_path = root / "sources" / "_provenance.jsonl"
    for f in sorted(files):
        event: dict = {
            "ts": ts,
            "source_id": source_id,
            "url": url,
            "local_path": f.relative_to(root).as_posix(),
            "sha256": sha256_file(f),
            "bytes": f.stat().st_size,
            "tool": tool,
        }
        if tool_version:
            event["tool_version"] = tool_version
        event["strategy"] = strategy
        if envelope:
            # `attempts` records that a lower rung had to be retried before it
            # held — the difference between "this came back first time" and
            # "this source is flaky", which only the ledger can remember.
            for key in ("canonical_url", "retrieved_at", "status", "mime",
                        "backend_ref", "attempts", "user_agent"):
                value = envelope.get(key)
                if value not in (None, "", [], {}):
                    event[key] = value
            if envelope.get("from_cache"):  # only the interesting signal: a store hit
                event["from_cache"] = True
        event["actor"] = actor
        if note:
            event["note"] = note
        append_jsonl(prov_path, event)

    # the page's primary artifact is the largest real capture, never the tiny
    # flip.json envelope sidecar (which is metadata, not content)
    primary = [f for f in files if f.name != "flip.json"] or files
    largest = max(primary, key=lambda p: p.stat().st_size)
    env_title = _plausible_title(envelope.get("title")) if envelope else None
    title = env_title or _title_for(target, capture_kind)
    fm: dict = {
        "type": "Source",
        "id": source_id,
        "aliases": [source_id],
        "title": title,
        "description": note or f"{kind} source",
    }
    if capture_kind == "config":
        canonical = envelope.get("canonical_url") if envelope else None
        # for copies the origin URI lives in provenance, not the page
        fm["resource"] = canonical.strip() if isinstance(canonical, str) and canonical.strip() \
            else url
    fm.update(
        {
            "local": largest.relative_to(root).as_posix(),
            "grade": "?",
            # No independence/freshness at capture: those are judgment keys
            # and capture confers nothing (SPEC §5.4). `flip grade` writes
            # them as the act of judgment.
            "status": "captured",
            "generated": {"by": actor, "at": utc_now()},
        }
    )

    ref_dir = root / "references"
    # File captures slug from the stem: `districts.csv` lives at
    # references/districts.md, not districts-csv.md (dogfood finding:
    # extension noise doubles up on .md captures — "…-survey-md.md").
    slug_source = Path(title).stem if capture_kind == "copy" else title
    slug = pages.unique_slug(ref_dir, pages.slugify(slug_source, fallback=source_id.lower()))
    body = f"# {title}\n" + (f"\n{note}\n" if note else "")
    hint = _hint_note(envelope)
    if hint:
        body += ("\n" if not body.endswith("\n") else "") + hint
    path = pages.write_page(ref_dir / f"{slug}.md", fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=path, fm=fm, body=body)


def source_pages(root: Path) -> list[pages.Page]:
    """Every source entity page under references/, filename order. Read-only
    helper for downstream consumers (claims, doctor, export); does not
    validate the notebook root — callers that mutate already have."""
    return pages.iter_pages(root, "references")


# Pipeline liveness values; `transferred:<steward>` is the prefixed form.
PIPELINES = ("live", "dormant", "orphaned")


def _find_source_page(root: Path, source_id: str) -> pages.Page:
    page = next((p for p in source_pages(root) if p.id == source_id), None)
    if page is None:
        known = ", ".join(p.id for p in source_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"unknown source id '{source_id}' in references/ (have: {known}) — "
            "run `flip add-source` first"
        )
    return page


def set_pipeline(root: Path, source_id: str, pipeline: str, evidence: str) -> pages.Page:
    """Record a source's pipeline liveness — staleness *classification*, not
    just age. `live | dormant | orphaned | transferred:<steward>`, and the
    evidence receipt is mandatory: an enum alone is not self-evidencing (the
    error four independent consumers repeated). Liveness belongs to the
    source, not the claim."""
    root = require_notebook_root(root)
    ok = pipeline in PIPELINES or (
        pipeline.startswith("transferred:") and pipeline.split(":", 1)[1].strip()
    )
    if not ok:
        raise SystemExit(
            f"invalid pipeline '{pipeline}' (one of: {', '.join(PIPELINES)}, "
            "or transferred:<steward>)"
        )
    evidence = (evidence or "").strip()
    if not evidence:
        raise SystemExit(
            "pipeline needs --evidence with a one-line receipt (no enum without evidence)"
        )
    page = _find_source_page(root, source_id)
    page.fm["pipeline"] = pipeline
    page.fm["pipeline_evidence"] = evidence
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def retitle_source(root: Path, source_id: str, title: str) -> pages.Page:
    """Rewrite a source's human-readable `title` (and its `# heading` when the
    body still carries the old one).

    The write path that keeps a bad capture title out of a text editor: a
    hand-edited frontmatter title is how an unquoted colon gets into YAML and
    breaks every reader of the notebook at once. flip's own writer quotes it.
    The slug is deliberately left alone — that is `flip rename`'s job, because
    moving a page has to rewrite the links pointing at it.
    """
    root = require_notebook_root(root)
    title = (title or "").strip()
    if not title:
        raise SystemExit("empty title; pass the name this source should carry")
    page = _find_source_page(root, source_id)
    old = str(page.fm.get("title") or "")
    page.fm["title"] = title
    body = page.body
    if old and body.startswith(f"# {old}"):
        body = f"# {title}" + body[len(f"# {old}"):]
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def recheck_source(root: Path, source_id: str, via: str | None = None) -> dict:
    """Re-fetch a URL-backed source's canonical coordinate and compare it
    against custody — the refresh receipt (SPEC §5.4).

    A page timestamp says the page changed; `last_checked` says the world
    was checked. The fetch lands in a temp directory — custody is never
    overwritten (a drift worth keeping is a fresh `flip add-source`
    capture). Appends a `recheck` event to the capture ledger
    ({ts, source_id, url, event, result: unchanged|changed|gone,
    sha256_now?, sha256_captured, actor}), stamps `last_checked`, and on
    changed/gone sets `drifted:` — doctor warns on the source and on
    load-bearing claims resting on it. Returns {result, url, sha256_now,
    baseline}.
    """
    root = require_notebook_root(root)
    page = _find_source_page(root, source_id)
    url = str(page.fm.get("resource") or page.fm.get("url") or "").strip()
    if not url:
        raise SystemExit(
            f"{source_id} has no URL coordinate (a copied local file); recheck applies "
            "to URL-backed captures — re-add the file to record a fresh capture"
        )
    local = str(page.fm.get("local") or "")
    baseline = None
    for ev in read_jsonl(root / "sources" / "_provenance.jsonl"):
        if str(ev.get("source_id")) == source_id and ev.get("sha256"):
            if not local or str(ev.get("local_path") or "") == local:
                baseline = str(ev["sha256"])
    if baseline is None:
        raise SystemExit(
            f"{source_id} has no recorded fixity in the capture ledger; nothing to "
            "compare against — capture it first with `flip add-source`"
        )
    kind = str(page.fm.get("kind") or "web")
    resolved = integrations.resolve("fetchers", "web" if kind == "file" else kind, via=via)
    result, sha_now, error = "gone", None, None
    with tempfile.TemporaryDirectory() as td:
        try:
            run = integrations.run_capture(resolved, Path(td), source_id, url)
            primary = [f for f in run.files if f.name != "flip.json"] or run.files
            largest = max(primary, key=lambda p: p.stat().st_size)
            sha_now = sha256_file(largest)
            result = "unchanged" if sha_now == baseline else "changed"
        except SystemExit as exc:
            error = str(exc)
    ts = utc_now()
    event: dict = {
        "ts": ts,
        "source_id": source_id,
        "url": url,
        "event": "recheck",
        "result": result,
        "sha256_captured": baseline,
    }
    if sha_now:
        event["sha256_now"] = sha_now
    if error:
        event["error"] = error
    event["actor"] = detect_actor()
    append_jsonl(root / "sources" / "_provenance.jsonl", event)
    page.fm["last_checked"] = ts
    if result in ("changed", "gone"):
        page.fm["drifted"] = result
    else:
        page.fm.pop("drifted", None)
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return {"result": result, "url": url, "sha256_now": sha_now, "baseline": baseline}


def set_provenance_state(
    root: Path, source_id: str, state: str, note: str | None = None
) -> pages.Page:
    """Record where the provenance chain-walk behind a source ended (SPEC
    §5.5, design D-B). PRIMARY-OPEN is a legitimate mid-pass state, but the
    doctor refuses done/published while a load-bearing claim rests on one."""
    root = require_notebook_root(root)
    if state not in PROVENANCE_STATES:
        raise SystemExit(
            f"invalid provenance state '{state}' (one of: {', '.join(PROVENANCE_STATES)})"
        )
    page = _find_source_page(root, source_id)
    page.fm["provenance_state"] = state
    if note:
        page.fm["provenance_note"] = note
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def list_sources(root: Path) -> list[dict]:
    """All sources as frontmatter dicts (+ slug and root-relative path), in id
    order. Read-only (backs `flip source list`)."""
    root = require_notebook_root(root)
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in source_pages(root)
    ]
    return sorted(rows, key=_id_sort_key)


def grade_source(
    root: Path,
    source_id: str,
    independence: str | None = None,
    basis: str | None = None,
    n: str | None = None,
    method: str | None = None,
    vintage: str | None = None,
    base_defined: bool | None = None,
    freshness: str | None = None,
    notes: str | None = None,
) -> pages.Page:
    """Record the support tuple on an existing page; returns the page.

    This IS the act of judgment (design D-A): independence is the tuple's
    spine and is required on first grading; basis/n/method/vintage/
    base_defined describe the evidence; the letter `grade` is (re)derived —
    never authored — and a migration seed is cleared by a real grading.
    Touches only the keys flip owns here; everything else round-trips
    untouched (SPEC §6.6), so an Obsidian-authored page survives.
    """
    root = require_notebook_root(root)
    for name, value, allowed in (
        ("independence", independence, INDEPENDENCE),
        ("basis", basis, BASES),
        ("freshness", freshness, FRESHNESS),
    ):
        if value is not None and value not in allowed:
            raise SystemExit(f"invalid {name} '{value}' (one of: {', '.join(allowed)})")
    page = next((p for p in source_pages(root) if p.id == source_id), None)
    if page is None:
        known = ", ".join(p.id for p in source_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"unknown source id '{source_id}' in references/ (have: {known}) — "
            "run `flip add-source` first"
        )
    if independence is None and not page.fm.get("independence"):
        raise SystemExit(
            f"{source_id} is unjudged and no --independence given; independence is the "
            f"judgment's spine (one of: {', '.join(INDEPENDENCE)})"
        )
    support = dict(_support(page.fm))
    support.pop("seeded", None)  # a real grading replaces any migration seed
    for key, value in (
        ("basis", basis), ("n", n), ("method", method),
        ("vintage", vintage), ("base_defined", base_defined),
    ):
        if value is not None:
            support[key] = value
    if support:
        page.fm["support"] = support
    if independence is not None:
        page.fm["independence"] = independence
    if freshness is not None:
        page.fm["freshness"] = freshness
    if notes is not None:
        page.fm["notes"] = notes
    page.fm["grade"] = derive_grade(page.fm)
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)
