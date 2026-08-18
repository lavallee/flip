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

`extract_text` is the write path for `flip extract` (SPEC §5.5): a *derivation*,
not a capture. It reads the raw bytes flip already holds, runs an
`[extractors]` command chosen by media family, writes `sources/text/<id>.txt`,
and appends one row to `derived/_derivations.jsonl` recording inputs → tool →
outputs with hashes and the extraction METHOD. `sources/raw/` is never touched.

Fetcher command templates and the capture runner live in `integrations` (SPEC
§15). A fetcher may hand back an optional neutral return envelope; when present,
its title/canonical_url flow onto the page and its strategy/retrieved_at/status/
backend_ref into provenance. Independence/freshness *hints* are recorded as a
page note only — grading stays a judgment made after reading, never auto-set.
"""

from __future__ import annotations

import json
import re
import shlex
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
    # The terminus, and the only rung that captures no bytes of the document:
    # custody holds flip's own record of the source and of the attempt. It is
    # not a rung you climb TO, it is where you stand when the ladder ran out
    # and the source still has to be citable (SPEC §5.1).
    "record-only",
)

# The methods above `record-only`, named in escalation order when an
# acquisition comes back empty-handed. `copy` is not a rung you can climb to
# from a URL, and `record-only` is the terminus, not a next step.
LADDER_RUNGS = tuple(m for m in CAPTURE_METHODS if m not in ("copy", "record-only"))

# Capture-log statuses that mean NO bytes landed. These rows are findings, not
# custody: they carry no sha256 and have no entity page by design, so every
# consumer that walks the ledger looking for captures has to skip them.
#
#   `failed`        the command could not run, or exited nonzero — an error.
#   `not-captured`  the command ran clean and found nothing — a finding about
#                   the document. Distinguishing the two is the whole point:
#                   one is a broken toolchain, the other is a gated source.
UNCAPTURED_STATUSES = ("failed", "not-captured")

# Statuses whose rows are NOT the source's capture, whether or not bytes
# landed. `refused` is the odd one: the fetcher delivered, and flip declined to
# open a page because the envelope described the acquisition in a word that
# isn't a method. The bytes are held and hashed (so they are not orphan
# custody), but nothing may read them as the capture — there is no page for
# them to be the capture OF.
NON_CAPTURE_STATUSES = (*UNCAPTURED_STATUSES, "refused")

# Methods that produce a page whose linked assets are NOT captured — the bytes
# are the document's text, not a faithful copy of what a reader saw.
_TEXT_ONLY_METHODS = ("http-get", "http-alt-representation", "archive-replay")

# Extraction methods (SPEC §5.5): HOW a text derivative was recovered from the
# raw bytes. Exactly the discipline CAPTURE_METHODS applies to acquisition,
# applied one layer down — because a quotation recovered by OCR is not the same
# evidence as one lifted from a publisher's own text layer, and until now a
# notebook had no way to say which. The derivation log already records the
# *actor* (`tool`, `tool_version`, `cmd`), so `method` is where the METHOD
# belongs: methods travel between deployments, tool names are local trivia.
#
# Not a ladder — these do not escalate. They are different acts on different
# inputs, and the right one is a fact about the document.
EXTRACTION_METHODS = (
    "text-layer",     # the document's own embedded text, as its producer wrote it
    "layout-text",    # that text plus geometric reconstruction of reading order
    "ocr",            # rendered to raster and recognized — a READING, not the text
    "markup-strip",   # markup reduced to prose
    "structured",     # an office/structured format's own text
    "transcript",     # speech recognized from media
)

# Below this, a derivative is `thin`. Calibrated on a real corpus rather than
# guessed: measured genuine extractions ran 391–994 words/page, and silent
# failures (a scan with no text layer, an extractor skipping pages, a
# classifier answering an extraction question) ran 0–10.8. Nothing landed in
# between, so the threshold sits in an empty band and is not a close call.
THIN_WORDS_PER_PAGE = 25.0

# The name of the metadata sidecar a fetcher may write into a capture dir. It
# is never the primary artifact — it is metadata about one (SPEC §15).
ENVELOPE_FILENAME = "flip.json"

# Suffix → media family for [extractors] routing. The INPUT FORMAT picks the
# extractor, not the source kind: a PDF is a PDF whether it was captured as a
# paper, a file, or a dataset. An unknown suffix becomes its own family, so an
# operator can configure `[extractors].epub` without flip learning about epub.
# Only suffixes that genuinely share a tool are collapsed. `.doc`/`.odt`/`.rtf`
# are deliberately NOT folded into `docx`: a tool that reads one of those often
# cannot read the others, and silently routing `.doc` at a docx-only lane would
# produce exactly the quiet failure this whole lane exists to catch. They fall
# through to their own family names and can be configured separately.
_MEDIA_FAMILIES = {
    ".pdf": "pdf",
    ".html": "html", ".htm": "html", ".xhtml": "html",
    ".docx": "docx",
    ".mp3": "audio", ".m4a": "audio", ".wav": "audio", ".flac": "audio",
    ".ogg": "audio", ".opus": "audio",
    ".mp4": "video", ".mkv": "video", ".mov": "video", ".webm": "video",
}

# Families whose bytes are a DOCUMENT a reader cannot read as they stand — the
# ones worth one nudge at capture time and one expected-until-use notice at
# doctor time. A .csv or a .json is already text; a .pdf is not. Both consumers
# also require a configured lane, so this list only has to be roughly right.
DOCUMENT_FAMILIES = (
    "pdf", "docx", "doc", "odt", "rtf", "xlsx", "pptx", "html", "epub",
    "audio", "video",
)

# Provenance terminal states (SPEC §5.4, design D-B): where the chain-walk
# behind this source ended. Optional; doctor gates done/published on OPEN.
PROVENANCE_STATES = (
    "PRIMARY-REACHED",
    "PRIMARY-GATED",
    "PRIMARY-LOST",
    "PRIMARY-NEVER-PUBLISHED",
    "PRIMARY-EXISTS-PRIVATE",
    "PRIMARY-OPEN",
)


def rungs_above(method: str) -> tuple[str, ...]:
    """The rungs a capture made with `method` has not tried yet.

    Naming the whole ladder back at someone who already climbed to
    `browser-render` is noise that teaches them to skip the line. An unknown
    method — or a `copy`, which is not on the ladder at all — gets the lot.
    """
    if method not in LADDER_RUNGS:
        return LADDER_RUNGS
    return LADDER_RUNGS[LADDER_RUNGS.index(method) + 1:]


def _support(fm: dict) -> dict:
    value = fm.get("support")
    return value if isinstance(value, dict) else {}


def capture_fidelity(event: dict) -> str:
    """What a capture event actually achieved — DERIVED from the ledger row,
    never stored (the same discipline as `derive_grade`).

    `faithful`   — assets inlined, a rendered page, or a verbatim local copy.
    `text-only`  — the document's text, but linked assets were not captured.
    `thin`       — succeeded and brought back almost nothing: a consent wall,
                   a JS shell, an error page served with status 200 — or a
                   `record-only` capture, which never held the document at
                   all. This is the dangerous one, because custody, a sha256
                   and a provenance row all look identical to a real capture.
    `unknown`    — no method recorded, or one outside the vocabulary.

    Callers pass one provenance event ({strategy, bytes, mime, …}).
    """
    method = str(event.get("strategy") or "")
    if method not in CAPTURE_METHODS:
        return "unknown"
    # A record capture never held the document, whatever its record.json
    # weighs — the fidelity is a fact about the method, not about the size.
    if method == "record-only":
        return "thin"
    # A registry record about a document is not the document. `publisher-api`
    # says so when only metadata was reachable; that is a real capture worth
    # keeping, and it is not the evidence someone will think it is.
    if str(event.get("status") or "") == "metadata-only":
        return "thin"
    size = event.get("bytes")
    mime = str(event.get("mime") or "")
    # A markup response carrying almost no payload didn't capture the document,
    # whatever the status line said. Non-markup (PDF, CSV) is legitimately small.
    #
    # The size test only makes sense for bytes a FETCH brought back: it is
    # looking for a consent wall or a JS shell standing in for the document.
    # Methods where a file was handed over — `copy`, and `human-in-loop` (a
    # person saved it, e.g. a short conversation) — have no such failure mode,
    # and inferring markup from a missing mime flagged every brief transcript
    # as thin. A declared markup mime still gets tested whatever the method.
    handed_over = method in ("copy", "human-in-loop")
    markup = "html" in mime or "xml" in mime or (not mime and not handed_over)
    if isinstance(size, int) and markup and size < 2048:
        return "thin"
    return "text-only" if method in _TEXT_ONLY_METHODS else "faithful"


def derivative_fidelity(row: dict) -> str:
    """What an extraction actually recovered — DERIVED from the derivation row,
    never authored (the same discipline as `capture_fidelity` and
    `derive_grade`).

    `text-only` — a real text derivative of the document.
    `thin`      — under 25 words/page (`THIN_WORDS_PER_PAGE`). The dangerous
                  one: unlike the empty case it leaves a plausible-looking
                  .txt on disk, with a sha256 and a derivation row, and
                  nothing about it says the pages are missing.
    `empty`     — no text at all. A `status: not-extracted` row, which by
                  design has no output file behind it.
    `unknown`   — a `method` outside EXTRACTION_METHODS, so what this text
                  even *is* cannot be read off the record.

    A row with no `method` is still judged on its words: the words-per-page
    evidence is a fact about the output and does not depend on the vocabulary.
    (`capture_fidelity` returns `unknown` for an absent method because its size
    test needs the method to mean anything; this one does not.)

    Callers pass one row from `derived/_derivations.jsonl`.
    """
    if str(row.get("status") or "") == "not-extracted":
        return "empty"
    words = 0
    for out in row.get("outputs") or []:
        if isinstance(out, dict) and isinstance(out.get("words"), int):
            words += out["words"]
    if words == 0:
        return "empty"
    method = str(row.get("method") or "")
    if method and method not in EXTRACTION_METHODS:
        return "unknown"
    pages_n = row.get("pages")
    if isinstance(pages_n, int) and pages_n > 0 and words / pages_n < THIN_WORDS_PER_PAGE:
        return "thin"
    return "text-only"


def media_family(path: Path | str) -> str:
    """The `[extractors]` key for a raw artifact: its media family.

    The input FORMAT picks the extractor, not the source kind — `.pdf` → `pdf`
    whether the page says paper, file, or dataset. An unrecognized suffix
    becomes its own family (`.epub` → `epub`), so an operator can configure a
    lane flip has never heard of and it routes with no code change.
    """
    suffix = Path(path).suffix.lower()
    return _MEDIA_FAMILIES.get(suffix, suffix.lstrip(".")) or "unknown"


def _primary_file(files: list[Path]) -> Path:
    """The primary artifact among a capture's files: the largest real one,
    never the `flip.json` envelope.

    One rule, three callers — `add_source` (picking the page's `local`),
    `primary_raw` (picking what `flip extract` reads), and, in ledger-row
    form, `latest_capture_event`. It was written out longhand in each of them
    until the extract lane needed a fourth copy.
    """
    real = [f for f in files if f.name != ENVELOPE_FILENAME] or files
    return max(real, key=lambda p: p.stat().st_size)


def primary_raw(root: Path, source_id: str) -> Path:
    """The raw artifact `flip extract` should read for `source_id`.

    Handles both custody shapes: a per-source directory
    (`sources/raw/<id>/…`, what a fetcher writes) and a loose file
    (`sources/raw/<id>.pdf`, what `builtin:copy` writes).
    """
    raw = root / "sources" / "raw"
    directory = raw / source_id
    if directory.is_dir():
        files = [f for f in directory.rglob("*") if f.is_file()]
        if not files:
            raise SystemExit(
                f"sources/raw/{source_id}/ holds no artifact to extract from — "
                f"the directory is empty; re-capture with `flip add-source`"
            )
        return _primary_file(files)
    loose = sorted(f for f in raw.glob(f"{source_id}.*") if f.is_file())
    if loose:
        return _primary_file(loose)
    raise SystemExit(
        f"no raw custody for {source_id} under sources/raw/ — extraction derives from "
        f"bytes flip holds, so capture it first with `flip add-source`. (A record "
        f"capture holds no document, and there is nothing in it to extract.)"
    )


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
    # A conversation is a spoken/written record like a talk, so it shares the
    # T class: the thing cited is an exchange, not a document (SPEC §8).
    "conversation": "T",
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


def _capture_record(
    root: Path, source_id: str, target: str, kind: str, note: str
) -> tuple[list[Path], str]:
    """builtin:record — the ladder's terminus written down (SPEC §5.1).

    No bytes of the document are obtained, because none were reachable. What
    lands in custody is flip's own record of the source and of the attempt:
    the coordinate, when it was recorded, by whom, and the note saying what was
    tried. That is a real artifact — it is the finding — and it is emphatically
    not the document, which is why the row derives `thin` fidelity and the page
    says so above the fold.
    """
    dest = root / "sources" / "raw" / source_id
    dest.mkdir(parents=True, exist_ok=True)
    payload = {
        "flip_record": 1,
        "target": target,
        "kind": kind,
        "recorded_at": utc_now(),
        "actor": detect_actor(),
        "note": note,
        "document_in_custody": False,
    }
    path = dest / "record.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return [path], target


def lane_inventory(kind: str, via: str | None) -> list[str]:
    """What else this machine has configured for capture, as guidance lines.

    flip cannot know what fills a lane (SPEC §16), but it can read the
    operator's own config and name the lanes, the kinds, and the binary behind
    the one that just came back empty. Naming the binary is the point: flip
    wires exactly ONE verb of whatever tool fills a role, and an agent that has
    only ever seen that verb will improvise around the tool instead of asking
    it for the rest of its surface.
    """
    lanes = integrations.capture_lanes()
    lines: list[str] = []
    used = via or "default"
    variants = [v for v in lanes.get(kind, []) if v != used]
    if variants:
        lines.append(
            f"    lanes configured for '{kind}' on this machine: "
            + ", ".join(f"--via {v}" for v in variants)
        )
    others = sorted(k for k in lanes if k != kind)
    if others:
        lines.append(
            f"    other kinds configured here: {', '.join(others)} — the same document "
            "often has a second coordinate"
        )
    return lines


def _empty_capture_guidance(
    exc: integrations.EmptyCapture, target: str, kind: str, via: str | None
) -> str:
    """The four moves that follow an empty-handed acquisition (SPEC §5.1).

    Climb, ask the tool for more, record it, or close it. Every one of them is
    a sanctioned move; none of them is "improvise your own fetch", which is
    what an agent does when the only thing flip says is that something might be
    wrong with the config.
    """
    quoted = shlex.quote(target)
    kind_flag = f" --kind {kind}"
    lines = [
        "the work goes on from here — SPEC §5.1, the ladder:",
        "  climb: the ladder, in escalation order — " + ", ".join(LADDER_RUNGS),
        *lane_inventory(kind, via),
        f"  ask the tool for more: this lane runs `{exc.tool}`, and flip wires one verb "
        f"of it. `{exc.tool} --help` may know how to search for, resolve, or route around "
        f"what this asked for; run it yourself and hand the result over with "
        f"`flip add-source <file>{kind_flag}`.",
        f"  record it: `flip add-source {quoted}{kind_flag} --record --note \"<rungs tried, "
        "what each returned>\"` opens a citable page for a document you do NOT hold — "
        "fidelity thin, grade ?, corroborating nothing until custody holds the document.",
        f"  close it: `flip pass {quoted} --reason \"<rungs tried, what each returned>\"` "
        "when the ladder is genuinely exhausted. \"Searched, gone\" is a finding, and it "
        "is worth more than a silent gap.",
    ]
    if exc.captures_stdout:
        lines.append(
            f"(the command in {integrations.config_path()} has no {{dest}} placeholder, so "
            f"flip watched {exc.tool}'s stdout for the artifact and it was empty. Add "
            "{dest} if it captures to a path of its own.)"
        )
    else:
        lines.append(
            f"(flip watched {exc.dest} and nothing appeared there. If {exc.tool} ignores "
            f"the {{dest}} it was passed and writes somewhere of its own choosing, fix that "
            f"in {integrations.config_path()} — but a clean exit with no output is more "
            "often the tool telling you it found nothing.)"
        )
    return "\n".join(lines)


def _regenerate_views(root: Path, changed: tuple[str, ...] | None = None) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root, changed=changed)


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
    """A fetcher-supplied title, or None when it isn't plausibly one — binary
    payload, a display truncation, a placeholder, or a metadata fragment."""
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
    # A trailing ellipsis is a display truncation, not a title: a fetcher that
    # clips for its own UI hands the clipped string over, and the ellipsis
    # bakes into canonical frontmatter and the slug (326/682 pages in one
    # measured corpus ended in "…").
    if text.endswith(("…", "...")):
        return None
    # "index" is a title only to the server that sent it. Eight sources in one
    # corpus shared the slug identity index-3…index-10 — the target-derived
    # name at least says which host's index this is.
    if text.lower() == "index":
        return None
    # JSON/bibtex metadata read as a title: {"title": "…"} or @article{…
    # handed over whole. The fragment names the record format, not the work.
    if text.startswith(("{", "@")) or '": "' in text:
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


def _record_refusal(
    root: Path,
    source_id: str,
    target: str,
    run: "integrations.CaptureRun",
    resolved,
    note: str | None,
) -> None:
    """Log a capture that succeeded and was refused for what it said about
    itself — one row per file that actually landed.

    The rows carry `local_path` and `sha256` because the bytes are really
    there: without them `flip doctor` reports each file as unregistered custody
    forever, and the operator is left with an accusation instead of a record.
    `status: refused` keeps them out of every consumer that walks the ledger
    for captures, and no entity page exists, so nothing can cite them.
    """
    ts = utc_now()
    actor = detect_actor()
    finding = (
        f"capture refused: the fetcher reported strategy {run.strategy!r}, which is "
        "not a capture method. The bytes were fetched and are held here, "
        "uncited, pending a fetcher fix"
    )
    for f in sorted(run.files):
        append_jsonl(
            root / "sources" / "_provenance.jsonl",
            {
                "ts": ts,
                "source_id": source_id,
                "url": target,
                "local_path": f.relative_to(root).as_posix(),
                "sha256": sha256_file(f),
                "bytes": f.stat().st_size,
                "status": "refused",
                "tool": run.tool,
                **({"tool_version": run.tool_version} if run.tool_version else {}),
                **({"via": resolved.name} if resolved and resolved.name else {}),
                "reported_strategy": run.strategy,
                "finding": finding,
                "actor": actor,
                **({"note": note} if note else {}),
            },
        )


def add_source(
    root: Path,
    target: str,
    kind: str | None = None,
    note: str | None = None,
    via: str | None = None,
    strategy: str | None = None,
    extra_fm: dict | None = None,
    record: bool = False,
) -> pages.Page:
    """Capture a source into the notebook; returns its new entity page.

    Routes by kind: "file" (or any kind whose configured fetcher is
    "builtin:copy") copies the file verbatim; everything else runs the
    [fetchers] command resolved from $FLIP_HOME/config.toml (optionally a named
    variant, `--via`). Appends one provenance event per captured file, opens
    references/<slug>.md at grade "?", touches the manifest. Local copies carry
    their origin file:// URI in provenance only; fetched targets also land on
    the page as `resource` (the fetcher's canonical_url when it reports one).

    `strategy` overrides the recorded capture method on the copy path only,
    for callers that know something the copy itself cannot show: a transcript
    handed over by the person who was in the conversation is `human-in-loop`,
    not the `copy` that moving the bytes would suggest (SPEC §5.1 — the record
    describes how the bytes were obtained, and a caller with better
    information is obliged to say so). Fetched captures report their own
    method and ignore this. `extra_fm` adds caller-owned frontmatter keys to
    the new page ahead of the custody keys.

    `record=True` skips acquisition entirely and writes a **record capture**
    (method `record-only`, SPEC §5.1): the ladder's terminus, for a source that
    exists and has to be citable but whose bytes are out of reach. It needs a
    `note` — the assertion "this was unreachable" is worthless without its
    receipt — and derives `thin` fidelity, so nothing downstream mistakes the
    record for the document.
    """
    root = require_notebook_root(root)
    kind = kind or _classify(target)
    if record:
        if not (note or "").strip():
            raise SystemExit(
                "a record capture needs --note: it asserts that the document itself was "
                "out of reach, and an assertion without its receipt is not a record. Say "
                "what was tried and what each rung returned, so the next reader (usually "
                "you) knows whether it is worth trying again"
            )
        if via is not None:
            raise SystemExit(
                f"--record does not run a fetcher, so --via {via!r} has nothing to select; "
                "drop one of them — --via to record the source, --record to stop trying"
            )
        if Path(target).expanduser().exists():
            raise SystemExit(
                f"'{target}' is a file on this machine — capture it (drop --record). A "
                "record capture says the document was out of reach, and this one is right "
                "here; recording it instead would put a falsehood in the ledger"
            )
    if strategy is not None and strategy not in CAPTURE_METHODS:
        raise SystemExit(
            f"invalid capture method '{strategy}' (one of: {', '.join(CAPTURE_METHODS)})"
        )
    source_id = pages.allocate_id(root, _ID_PREFIXES.get(kind, "S"))

    # Route on the TARGET, not only the kind: `--kind dataset ./local.psv` used
    # to demand a [fetchers] command for a file already on disk, while the same
    # path with `--kind file` copied fine. A local path never needs a fetcher.
    local_target = Path(target).expanduser().exists()
    resolved = (
        None if record or kind == "file" or local_target
        else integrations.resolve("fetchers", kind, via=via)
    )
    envelope: dict | None = None
    if record:
        files, url = _capture_record(root, source_id, target, kind, str(note))
        tool, tool_version, capture_kind, strategy = (
            "builtin:record", None, "record", "record-only",
        )
    elif resolved is None or resolved.template == "builtin:copy":
        files, origin = _capture_copy(root, source_id, target)
        tool, tool_version, capture_kind, strategy, url = (
            "builtin:copy", None, "copy", strategy or "copy", origin,
        )
    else:
        try:
            run = integrations.run_capture(resolved, root, source_id, target)
        except integrations.EmptyCapture as exc:
            # The tool ran fine and found nothing. That is a finding ABOUT THE
            # DOCUMENT — gated, withdrawn, not served to us — and the honest
            # ledger status is `not-captured`, not `failed`: nothing here is
            # broken. The refusal still propagates, carrying the ladder with it.
            append_jsonl(
                root / "sources" / "_provenance.jsonl",
                {
                    "ts": utc_now(),
                    "source_id": source_id,
                    "url": target,
                    "status": "not-captured",
                    "tool": exc.tool,
                    **({"via": resolved.name} if resolved.name else {}),
                    "finding": str(exc),
                    "actor": detect_actor(),
                    **({"note": note} if note else {}),
                },
            )
            raise SystemExit(
                f"{exc}\n{_empty_capture_guidance(exc, target, kind, via)}"
            ) from None
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
        # The envelope is untrusted input and this is the trust boundary,
        # exactly as it is for --strategy above: a fetcher reporting a word
        # outside the method vocabulary is usually reporting its own NAME (a
        # measured corpus held `direct`, `googlebot`, `pdf` — tool trivia, not
        # methods). Refusing keeps two notebooks comparable across deployments;
        # accepting it silently is how one corpus accrued 520 warnings.
        #
        # Deliberately OUTSIDE the try: the acquisition succeeded, and routing
        # this through the `failed` handler would write the one thing the
        # ledger must never say — that the fetcher looked and came back
        # empty-handed, when it looked and delivered.
        if run.strategy is not None and run.strategy not in CAPTURE_METHODS:
            _record_refusal(root, source_id, target, run, resolved, note)
            raise SystemExit(
                f"fetcher for kind '{kind}' reported capture strategy "
                f"{run.strategy!r}, which is not a capture method (one of: "
                f"{', '.join(CAPTURE_METHODS)}). The provenance ledger records "
                "the METHOD there — the tool's name already lands in `tool`. "
                "Fix the fetcher's envelope, or drop its `strategy` key to "
                "record the method as unreported.\n"
                f"The bytes it fetched are held at sources/raw/{source_id}/ and "
                "logged as a refused capture — no page was opened, so nothing "
                "cites them. Re-run once the fetcher is fixed, or delete that "
                "directory."
            )
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
        if strategy is not None:
            # No key when the fetcher reported no method: absence is the true
            # record (capture_fidelity derives `unknown` from it), where any
            # invented word would be the misdescription SPEC §5.1 forbids.
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
    largest = _primary_file(files)
    env_title = _plausible_title(envelope.get("title")) if envelope else None
    title = env_title or _title_for(target, capture_kind)
    fm: dict = {
        "type": "Source",
        "id": source_id,
        "aliases": [source_id],
        "title": title,
        "description": note or f"{kind} source",
    }
    if extra_fm:
        fm.update({k: v for k, v in extra_fm.items() if v not in (None, "", [], {})})
    if capture_kind in ("config", "record"):
        canonical = envelope.get("canonical_url") if envelope else None
        # for copies the origin URI lives in provenance, not the page; a record
        # capture is nothing BUT the coordinate, so it always carries it
        fm["resource"] = canonical.strip() if isinstance(canonical, str) and canonical.strip() \
            else url
    fm.update(
        {
            "local": largest.relative_to(root).as_posix(),
            "grade": "?",
            # No independence/freshness at capture: those are judgment keys
            # and capture confers nothing (SPEC §5.4). `flip grade` writes
            # them as the act of judgment.
            #
            # `recorded` is not `captured`, and the page says so at rest: what
            # is in custody is the record of a source, not the source.
            "status": "recorded" if capture_kind == "record" else "captured",
            "generated": {"by": actor, "at": utc_now()},
        }
    )

    ref_dir = root / "references"
    # File captures slug from the stem: `districts.csv` lives at
    # references/districts.md, not districts-csv.md (dogfood finding:
    # extension noise doubles up on .md captures — "…-survey-md.md").
    slug_source = Path(title).stem if capture_kind == "copy" else title
    slug = pages.unique_slug(
        ref_dir, pages.slugify(slug_source, fallback=source_id.lower()), entity_id=source_id
    )
    body = f"# {title}\n" + (f"\n{note}\n" if note else "")
    if capture_kind == "record":
        # Above the fold, in the reader's own words-per-minute: the one thing
        # that must not be missed about this page is what is NOT behind it.
        body += (
            "\n> **Record capture — the document itself is not in custody.** What is "
            "held is flip's record of the source and of the attempt (`record-only`, "
            "SPEC §5.1), which derives `thin` fidelity. Do not cite this as though you "
            "read it. If a rung above opens later, capture the document and this page "
            "is superseded by that capture.\n"
        )
    hint = _hint_note(envelope)
    if hint:
        body += ("\n" if not body.endswith("\n") else "") + hint
    path = pages.write_page(ref_dir / f"{slug}.md", fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root, changed=("references",))
    return pages.Page(path=path, fm=fm, body=body)


def latest_capture_event(root: Path, source_id: str) -> dict | None:
    """The capture-log row for a source's PRIMARY artifact, most recent first —
    the row `capture_fidelity` should be asked about.

    The ledger-row form of `_primary_file`'s rule: the `flip.json` envelope is
    metadata rather than content, and among the real files the largest is the
    document. Rows with no bytes (a failed or empty acquisition, a recheck
    receipt) are not captures and are skipped.
    """
    best: dict | None = None
    for event in read_jsonl(root / "sources" / "_provenance.jsonl"):
        if str(event.get("source_id") or "") != source_id or not event.get("sha256"):
            continue
        if str(event.get("status") or "") in NON_CAPTURE_STATUSES:
            continue
        if Path(str(event.get("local_path") or "")).name == ENVELOPE_FILENAME:
            continue
        if best is None or str(event.get("ts") or "") > str(best.get("ts") or ""):
            best = event
        elif event.get("ts") == best.get("ts") and (event.get("bytes") or 0) > (
            best.get("bytes") or 0
        ):
            best = event
    return best


# --- text derivatives (SPEC §5.5) ------------------------------------------

DERIVATIONS = Path("derived") / "_derivations.jsonl"

# Derivation-log statuses that mean NO derivative landed. Exactly the shape of
# UNCAPTURED_STATUSES one layer down, and for the same reason: the two ways of
# getting nothing are different events and must stay distinguishable.
#
#   `failed`         the extractor could not run, or exited nonzero.
#   `not-extracted`  it ran clean and found no text — a fact about the DOCUMENT.
UNEXTRACTED_STATUSES = ("failed", "not-extracted")


def page_count(path: Path) -> int | None:
    """Best-effort page count for the words-per-page test; None when unknown.

    PDFs only, and deliberately crude: count the `/Type /Page` objects and
    subtract the `/Type /Pages` tree nodes. A PDF that keeps its objects in a
    compressed object stream hides both, and then this returns None and the
    thin test simply does not run — which is the right failure. flip will not
    take a PDF library dependency to sharpen a heuristic whose only job is to
    decide whether to print a warning.
    """
    if path.suffix.lower() != ".pdf":
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    leaves = data.count(b"/Type /Page") + data.count(b"/Type/Page")
    trees = data.count(b"/Type /Pages") + data.count(b"/Type/Pages")
    return (leaves - trees) or None


def _template_tool(template: str) -> str:
    """The binary a command template runs, for a ledger row written before (or
    instead of) a successful run."""
    tokens = integrations._tokenize_template(template)
    return Path(tokens[0]).name if tokens else template.strip()


def latest_derivation(root: Path, source_id: str, kind: str = "text") -> dict | None:
    """The most recent derivation row for a source, or None.

    Rows that landed nothing (`failed`, `not-extracted`) are findings rather
    than derivatives and are skipped — the same rule `latest_capture_event`
    applies to the capture log, so a source whose only extraction attempt came
    back empty reads as *having no derivative*, which is the truth.
    """
    best: dict | None = None
    for row in read_jsonl(root / DERIVATIONS):
        if str(row.get("source_id") or "") != source_id:
            continue
        if str(row.get("kind") or "") != kind:
            continue
        if str(row.get("status") or "") in UNEXTRACTED_STATUSES:
            continue
        if not row.get("outputs"):
            continue
        if best is None or str(row.get("ts") or "") >= str(best.get("ts") or ""):
            best = row
    return best


def extraction_lane_inventory(family: str, via: str | None) -> list[str]:
    """The other extract lanes this machine has, as guidance lines.

    The twin of `lane_inventory`, and the reason "hunt around for an OCR tool"
    stops being a thing an agent does from memory: flip may not know what fills
    a lane (SPEC §16), but it can read the operator's own config back to them
    and print the runnable command.
    """
    lanes = integrations.extraction_lanes()
    lines: list[str] = []
    used = via or "default"
    variants = [v for v in lanes.get(family, []) if v != used]
    if variants:
        lines.append(
            f"    other '{family}' lanes configured on this machine: "
            + ", ".join(f"--via {v}" for v in variants)
        )
    others = sorted(k for k in lanes if k != family)
    if others:
        lines.append(f"    other media families configured here: {', '.join(others)}")
    return lines


def extraction_guidance(
    source_id: str, family: str, via: str | None, method: str | None
) -> str:
    """What remains after an extraction came back with nothing (or nearly).

    Every line is a sanctioned move. None of them is "render the pages and run
    an OCR binary by hand in a shell loop", which is what happens when the only
    thing flip says is that something might be wrong.
    """
    lines = [
        "the work goes on from here — SPEC §5.5:",
        f"  custody is intact: sources/raw/ is untouched and {source_id} is still "
        "citable. What is missing is the readable derivative, not the source.",
        "  extraction methods, and what each one is for — "
        + ", ".join(EXTRACTION_METHODS),
    ]
    inventory = extraction_lane_inventory(family, via)
    if inventory:
        lines.append(f"  try another lane: flip extract {source_id} --via <name>")
        lines.extend(inventory)
    else:
        lines.append(
            f"  no other [extractors].{family} lane is configured on this machine. A "
            f"document with no text layer needs an `ocr` lane; add one to "
            f"{integrations.config_path()} and re-run "
            f"(`flip extract {source_id} --via ocr --method ocr`)."
        )
    if method != "ocr":
        lines.append(
            "  if it is an image-only scan, no text-layer tool will ever find words in "
            "it — that is a fact about the document, and OCR is the only answer."
        )
    lines.append(
        "  flip wires exactly ONE verb of whatever fills this lane; that binary's "
        "`--help` may have modes flip never calls. Run it yourself and hand the "
        f"result back with `flip extract {source_id}` once the lane is right."
    )
    lines.append(
        f"  or read it yourself: sources/raw/ holds the bytes, and a source with no "
        f"text derivative is still a source. {source_id} is not damaged by this."
    )
    return "\n".join(lines)


def extract_text(
    root: Path,
    source_id: str,
    via: str | None = None,
    force: bool = False,
    note: str | None = None,
    method: str | None = None,
) -> dict:
    """Derive `sources/text/<id>.txt` from a source's raw bytes; return the row.

    The write path for `flip extract`. Routes on the raw artifact's **media
    family** (`pdf`, `html`, `docx`, `audio`) to an `[extractors]` command from
    `$FLIP_HOME/config.toml`, runs it with `{src}`/`{out}`/`{id}`, and appends
    exactly one row to `derived/_derivations.jsonl` — inputs with hashes, the
    tool and the verbatim command template, the method, outputs with hashes and
    a word count, and `supersedes` naming the previous derivative it replaces.

    **`sources/raw/` is never touched.** A derivative is not raw and may be
    overwritten; what makes that safe is the append-only log. If the file on
    disk hashes to no row in it, a human edited it by hand and this refuses
    without `force` — the log is what lets flip tell its own last output from
    someone else's work.

    `method` is the extraction METHOD (SPEC §5.5), and flip will not guess one:
    when it isn't given, a lane *named* after a method supplies it (a `--via
    ocr` lane records `ocr`) and otherwise no method is recorded at all.
    Defaulting to `text-layer` would be a lie in exactly the case that matters.

    Raises `SystemExit` when the extractor could not run or failed, and when it
    ran clean and produced no text — the second carrying the operator's own
    lanes, because that one is a finding about the document.
    """
    root = require_notebook_root(root)
    if method is not None and method not in EXTRACTION_METHODS:
        raise SystemExit(
            f"invalid extraction method '{method}' (one of: "
            f"{', '.join(EXTRACTION_METHODS)}) — the method says how the text was "
            "recovered, and a quotation lifted from a publisher's text layer is not "
            "the same evidence as one an OCR engine read off a scan"
        )
    src = primary_raw(root, source_id)
    if src.name == "record.json" and b'"flip_record"' in src.read_bytes():
        # A record capture holds flip's record of a source and of the attempt to
        # get it — never the document (SPEC §5.1). Running an extractor over the
        # record would produce a text derivative *of flip's own note*, which is
        # the one output nobody could safely quote.
        raise SystemExit(
            f"{source_id} is a record capture: custody holds flip's record of the source "
            "and of the attempt, not the document, so there is no text in it to extract. "
            "Climb the ladder again (SPEC §5.1) and capture the document; extracting the "
            "record would produce a derivative of flip's own note about the failure"
        )
    family = media_family(src)
    resolved = integrations.resolve("extractors", family, via=via)
    # A lane named after a method IS the method — `[extractors.pdf].ocr` says
    # what it does, and making the operator repeat it in --method every time is
    # how a field goes unfilled.
    if method is None and resolved.name in EXTRACTION_METHODS:
        method = resolved.name

    out = root / "sources" / "text" / f"{source_id}.txt"
    log = root / DERIVATIONS
    prior = [
        r for r in read_jsonl(log)
        if str(r.get("source_id") or "") == source_id and str(r.get("kind") or "") == "text"
    ]
    known_outputs = [
        o for r in prior for o in (r.get("outputs") or []) if isinstance(o, dict)
    ]

    # Something is at the output path and it is not a file. An extractor whose
    # flags were misread can make one: a lane configured with a tool whose `-o`
    # means output DIRECTORY created sources/text/<id>.txt as a directory, and
    # the next run died inside the tool on IsADirectoryError — a stack trace
    # where a flip refusal belonged, blaming the retry for what the first run
    # left behind. Neither --force nor the hand-edit guard below covers this,
    # because the question is not whose bytes those are; there are no bytes.
    if out.exists() and not out.is_file():
        kind = "a directory" if out.is_dir() else "not a regular file"
        raise SystemExit(
            f"sources/text/{source_id}.txt exists and is {kind}, so nothing can be "
            "written there. flip did not create it — an extractor did, and almost "
            "always because a lane passes {out} to a flag that means output DIRECTORY "
            "rather than output file.\n"
            f"  check the lane: flip config show  (the [extractors].{family} entry)\n"
            f"  then clear the path: rm -r {out.relative_to(root).as_posix()}\n"
            "  a tool that only writes to a directory, or only to stdout, still fits: "
            "omit {out} from the template and flip preserves stdout"
        )

    if out.is_file() and not force:
        if sha256_file(out) not in {o.get("sha256") for o in known_outputs}:
            raise SystemExit(
                f"sources/text/{source_id}.txt exists and its sha256 matches no row in "
                f"{DERIVATIONS.as_posix()} — flip did not write the bytes that are there, "
                "so a person did: a hand correction, a stitched-together transcript, a "
                "paste from somewhere else. Re-extracting would discard it silently and "
                "the log would show only the replacement.\n"
                f"  keep the edit: leave it alone, or move it somewhere flip does not own.\n"
                f"  replace it anyway: flip extract {source_id} --force "
                '--note "<what the hand edit was, and why it goes>"'
            )

    ts = utc_now()
    row: dict = {
        "ts": ts,
        "source_id": source_id,
        "kind": "text",
        "inputs": [{
            "path": src.relative_to(root).as_posix(),
            "sha256": sha256_file(src),
            "bytes": src.stat().st_size,
        }],
        # The command template goes in verbatim — placeholders and all — so the
        # row says what was configured, not just what it expanded to on this
        # machine. `tool` is refined to the real argv[0] once the run returns.
        "tool": _template_tool(resolved.template),
        "cmd": resolved.template,
    }
    if resolved.name:
        row["via"] = resolved.name
    if method:
        row["method"] = method
    if note:
        row["note"] = note
    row["actor"] = detect_actor()

    try:
        run = integrations.run_extraction(resolved, root, source_id, src, out)
    except integrations.EmptyExtraction as exc:
        # Ran clean, found no text. A finding about the DOCUMENT — an image-only
        # scan, a form with no content — so the honest status is `not-extracted`
        # and nothing here is broken. No output file is written (run_extraction
        # restores what was there), because an empty .txt on disk is the one
        # artifact that would read as a successful extraction.
        pages_n = page_count(src)
        row["status"] = "not-extracted"
        row["finding"] = str(exc) + (f" ({pages_n} pages)" if pages_n else "")
        if pages_n:
            row["pages"] = pages_n
        append_jsonl(log, row)
        raise integrations.EmptyExtraction(
            f"{row['finding']}\n{extraction_guidance(source_id, family, via, method)}",
            key=exc.key, src=exc.src, out=exc.out, tool=exc.tool,
            template=exc.template, captures_stdout=exc.captures_stdout,
        ) from None
    except SystemExit as exc:
        # A failed extraction is a finding too: the attempt lands in the ledger
        # so "tried and it broke" stays distinguishable from "never tried".
        row["status"] = "failed"
        row["error"] = str(exc)
        append_jsonl(log, row)
        raise

    row["tool"] = Path(run.tool).name
    if run.tool_version:
        row["tool_version"] = run.tool_version
    pages_n = page_count(src)
    row["outputs"] = [{
        "path": out.relative_to(root).as_posix(),
        "sha256": sha256_file(out),
        "bytes": out.stat().st_size,
        "words": run.words,
    }]
    if pages_n:
        row["pages"] = pages_n
        row["words_per_page"] = round(run.words / pages_n, 1)
    # `fidelity` is NOT written. It is derived on every read by
    # `derivative_fidelity(row)`, exactly as `capture_fidelity` is derived from
    # a capture row and `derive_grade` from a support tuple — flip stores the
    # description and computes the summary, never the reverse.
    #
    # The tempting argument for storing it is that the inputs (`words`,
    # `pages`, `method`) sit in this same append-only row, so the two could
    # never drift. That argument defeats itself: a value that cannot drift from
    # its inputs is a value the reader can always recompute, and writing it
    # down buys nothing while adding the one thing doctor has a check against
    # elsewhere (`grade-drift`) — a stored derivation.
    if known_outputs:
        row["supersedes"] = known_outputs[-1].get("sha256")
    append_jsonl(log, row)
    # The mutation tail, minus the regenerate: extraction writes no page and
    # changes no listing, so `views.regenerate` would rewrite generated files
    # to identical content on every run. The notebook did change, so `updated`
    # moves.
    manifest.touch_updated(root)
    return row


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
            sha_now = sha256_file(_primary_file(run.files))
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
    §5.4, design D-B). PRIMARY-OPEN is a legitimate mid-pass state, but the
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
