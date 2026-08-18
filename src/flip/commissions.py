"""Commission contracts as entity pages — commissions/<slug>.md (SPEC §7).

A commission is bounded follow-up work, written as a contract BEFORE
dispatch: what it must consume (`universe`), what it must produce (the
deliverable, the page body), when it stops (`stop`), and what it must not
re-search (`does_not_redo`). The four fields exist because chains that
carried them consumed prior outputs without re-discovery, and chains
without them re-searched what they already held. The optional ROI band is
directional and never additive across commissions; the working convention
is to quote the LOW bound as the expectation and the range as upside —
executed estimates to date held at their low bound.

A commission page records a contract and its outcome; nothing here
dispatches anything. Lifecycle: proposed → dispatched → returned |
declined. A return carries `consumed` — what prior output the run consumed
— the one-line receipt that keeps continuation chains auditable. Ids (K#)
are never reused: allocation goes through pages.allocate_id like every
other entity.
"""

from __future__ import annotations

from pathlib import Path

from . import manifest, pages, util, views

STATUSES = ("proposed", "dispatched", "returned", "declined")

# Legal moves. Terminal states have no exits: a returned commission that
# spawns more work gets a NEW commission (contracts are append-only in
# spirit — rewriting a settled one would rewrite what was agreed).
_TRANSITIONS = {
    "proposed": ("dispatched", "declined"),
    "dispatched": ("returned", "declined"),
    "returned": (),
    "declined": (),
}

LOG = Path("log") / "log.jsonl"


def _log_event(root: Path, event: str, kid: str, detail: str) -> None:
    util.append_jsonl(
        root / LOG,
        {
            "ts": util.utc_now(),
            "text": f'{event} {kid}: "{detail}"',
            "actor": util.detect_actor(),
        },
    )


def _find_commission(root: Path, kid: str) -> pages.Page:
    """The Commission page for `kid`, refusing everything else.

    find_by_id resolves across every scanned dir, so without the type check a
    typo'd id (H1, C1) would hand the lifecycle a hypothesis or claim page to
    mutate — the status write would corrupt a foreign entity silently.
    """
    page = pages.find_by_id(root, kid)
    if page is not None and str(page.fm.get("type", "")) != "Commission":
        raise SystemExit(
            f"'{kid}' is {page.fm.get('type') or 'an untyped page'} "
            f"({page.path.name}), not a commission; commission ids are K#"
        )
    if page is None:
        known = sorted(
            (p.id for p in pages.iter_pages(root, "commissions") if p.id),
            key=lambda s: (len(s), s),
        )
        hint = (
            f"known: {', '.join(known)}"
            if known
            else 'none recorded yet; add one with `flip commission add "<deliverable>" …`'
        )
        raise SystemExit(f"no commission '{kid}' in commissions/ ({hint})")
    return page


def add_commission(
    root: Path,
    deliverable: str,
    universe: str,
    stop: str,
    does_not_redo: str,
    for_ref: str | None = None,
    roi_low: str | None = None,
    roi_high: str | None = None,
) -> pages.Page:
    """Write a commission contract (status "proposed"), allocating the next K#.

    All four contract fields are required — a commission without an input
    universe, stop condition, or does-not-redo boundary is a wish with a
    deliverable attached. `for_ref` links the question or thread this serves
    (must resolve). ROI stays free text and optional; when only one bound is
    known it is the low one (the expectation).
    """
    root = util.require_notebook_root(root)
    deliverable = _require(deliverable, "deliverable")
    universe = _require(universe, "input universe")
    stop = _require(stop, "stop condition")
    does_not_redo = _require(does_not_redo, "does-not-redo boundary")
    if roi_high and not roi_low:
        raise SystemExit(
            "--roi-high given without --roi-low; the low bound is the "
            "expectation — quote it first (or alone)"
        )
    if for_ref is not None:
        for_ref = for_ref.strip()
        if pages.find_by_id(root, for_ref) is None:
            raise SystemExit(f"unknown ref '{for_ref}' for --for; it must resolve in "
                             "this notebook")
    kid = pages.allocate_id(root, "K")
    fm: dict = {
        "type": "Commission",
        "id": kid,
        "aliases": [kid],
        "description": _describe(deliverable),
        "status": "proposed",
        "universe": universe,
        "stop": stop,
        "does_not_redo": does_not_redo,
    }
    if for_ref:
        fm["for"] = for_ref
    if roi_low:
        fm["roi_low"] = str(roi_low)
        if roi_high:
            fm["roi_high"] = str(roi_high)
    fm["generated"] = util.generated_now()
    directory = root / "commissions"
    slug = pages.unique_slug(
        directory, pages.slugify(deliverable, fallback=kid.lower()), entity_id=kid
    )
    path = pages.write_page(directory / f"{slug}.md", fm, deliverable + "\n")
    _log_event(root, "commission-add", kid, _describe(deliverable))
    _finish(root)
    return pages.Page(path=path, fm=fm, body=deliverable + "\n")


def set_commission_status(
    root: Path,
    kid: str,
    status: str,
    note: str | None = None,
    consumed: str | None = None,
) -> pages.Page:
    """Move a commission along its lifecycle, refusing illegal jumps.

    `returned` asks for `consumed` — what prior output the run consumed, the
    receipt that keeps a continuation chain auditable (a return without one
    is accepted but says so). Every move lands a dated body section and a
    `commission-status` log event.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid status '{status}' (one of: {', '.join(STATUSES)})")
    page = _find_commission(root, kid)
    current = str(page.fm.get("status", "proposed"))
    if status == current:
        raise SystemExit(f"commission {kid} is already {status}; nothing to do")
    allowed = _TRANSITIONS.get(current, ())
    if status not in allowed:
        exits = ", ".join(allowed) if allowed else "none — terminal; open a new commission"
        raise SystemExit(
            f"commission {kid} is {current}; legal moves: {exits}"
        )
    if consumed is not None and status != "returned":
        raise SystemExit("--consumed belongs to a return; pass it with status 'returned'")
    page.fm["status"] = status
    heading = f"{status.capitalize()} {util.today()}"
    parts = []
    if consumed and consumed.strip():
        page.fm["consumed"] = consumed.strip()
        parts.append(f"Consumed: {consumed.strip()}")
    if note and note.strip():
        parts.append(note.strip())
    body = _append_section(page.body, heading, "\n\n".join(parts) or None)
    pages.write_page(page.path, page.fm, body)
    _log_event(root, "commission-status", kid, status)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def list_commissions(root: Path, status: str | None = None) -> list[dict]:
    """Every commission page as a plain dict, in contract (id) order."""
    if status is not None and status not in STATUSES:
        raise SystemExit(f"invalid status '{status}' (one of: {', '.join(STATUSES)})")
    rows = []
    for page in pages.iter_pages(root, "commissions"):
        if str(page.fm.get("type", "")) != "Commission":
            continue
        row = {
            "id": page.id,
            "slug": page.slug,
            "path": page.path.relative_to(root).as_posix(),
            "deliverable": str(page.fm.get("description", "")),
            "status": str(page.fm.get("status", "proposed")),
            "universe": str(page.fm.get("universe", "")),
            "stop": str(page.fm.get("stop", "")),
            "does_not_redo": str(page.fm.get("does_not_redo", "")),
        }
        for key in ("for", "roi_low", "roi_high", "consumed"):
            if page.fm.get(key):
                row[key] = str(page.fm[key])
        rows.append(row)
    rows.sort(key=lambda r: _id_num(r["id"]))
    if status is not None:
        rows = [r for r in rows if r["status"] == status]
    return rows


def _require(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"empty {what}; a commission without one is a wish — write it")
    return value


def _describe(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _append_section(body: str, heading: str, text: str | None) -> str:
    base = body.rstrip("\n")
    section = f"## {heading}" + (f"\n{text}" if text else "")
    return (base + "\n\n" if base else "") + section + "\n"


def _id_num(entity_id: str) -> int:
    digits = "".join(ch for ch in entity_id if ch.isdigit())
    return int(digits) if digits else 0


def _finish(root: Path) -> None:
    manifest.touch_updated(root)
    # Both mutations here write one commissions/ page (plus a log event, which
    # regenerate always re-renders); nothing else needs recounting.
    views.regenerate(root, changed=("commissions",))
