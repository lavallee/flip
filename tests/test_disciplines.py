"""Tests for flip.disciplines — the Phase 3 composition layer
(design-composition-0.14.md).

Loader precedence and aka, pin parsing (bare-major prefers the highest
minor), the three built-ins' shapes, the byte-identical dormancy acceptance
test, owner labeling on explicit declare, slot-conflict resolution, graceful
dependencies, the slot near-miss advisory, field predicates (enforced /
advisory / attested), kind slot requirements, render/2 and okf carriage,
CLI round-trips, the scaffold, and CHECK_CODES completeness.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import disciplines, kinds, pages, scaffold
from flip.cli import main
from flip.doctor import CHECK_CODES, run_doctor
from flip.export import export_json
from flip.manifest import load_manifest, save_manifest

DOCTOR_PY = Path(__file__).resolve().parent.parent / "src" / "flip" / "doctor.py"

DISCIPLINE_CODES = (
    "unknown-discipline", "discipline-moved", "bad-discipline", "unresolved-slot",
    "discipline-dependency", "slot-name-mismatch", "slot-unfilled",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(tmp_path: Path, kind: str = "scout", slug: str = "demo") -> Path:
    return scaffold.create_notebook(tmp_path / slug, slug, kind)


def declare(root: Path, pins: list[str], resolve: dict | None = None) -> None:
    m = load_manifest(root)
    m.disciplines = pins
    if resolve is not None:
        m.discipline_resolve = resolve
    save_manifest(root, m)


def write_user_discipline(tmp_path: Path, name: str, text: str) -> Path:
    user_dir = tmp_path / "fliphome" / "disciplines"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- loader / precedence


def test_list_disciplines_includes_three_builtins():
    rows = {d.id: d for d in disciplines.list_disciplines()}
    assert rows["lineage"].origin == "built-in"
    assert rows["lineage"].version == "1.1"
    assert rows["forecasting"].version == "1.0"
    assert rows["systematic-screening"].version == "0.1"
    for d in rows.values():
        assert d.kind == "regime"


def test_load_discipline_unknown_lists_known_ids():
    with pytest.raises(SystemExit) as exc:
        disciplines.load_discipline("no-such-discipline")
    assert "unknown discipline" in str(exc.value)
    assert "lineage" in str(exc.value)


def test_discipline_exists():
    assert disciplines.discipline_exists("lineage")
    assert not disciplines.discipline_exists("no-such-discipline")


def test_user_dir_single_file_and_directory_form_are_equivalent(tmp_path):
    single = (
        'id = "single-form"\nversion = "0.1"\nkind = "regime"\nsummary = "s"\n\n'
        '[[slot]]\nid = "area"\n'
    )
    write_user_discipline(tmp_path, "single-form", single)
    dir_form = tmp_path / "fliphome" / "disciplines" / "dir-form"
    dir_form.mkdir(parents=True)
    (dir_form / "discipline.toml").write_text(
        single.replace('"single-form"', '"dir-form"'), encoding="utf-8"
    )
    d1 = disciplines.load_discipline("single-form")
    d2 = disciplines.load_discipline("dir-form")
    assert d1.origin == d2.origin == "user"
    assert [s.id for s in d1.slots] == [s.id for s in d2.slots] == ["area"]


def test_precedence_user_overrides_builtin(tmp_path):
    write_user_discipline(
        tmp_path, "lineage",
        'id = "lineage"\nversion = "1.1"\nkind = "regime"\nsummary = "overridden"\n',
    )
    d = disciplines.load_discipline("lineage")
    assert d.version == "1.1"
    assert d.origin == "user"


def test_precedence_notebook_overrides_user(tmp_path):
    write_user_discipline(
        tmp_path, "custom",
        'id = "custom"\nversion = "0.1"\nkind = "regime"\nsummary = "user"\n',
    )
    root = tmp_path / "nb"
    nb_dir = root / ".flip" / "disciplines"
    nb_dir.mkdir(parents=True)
    (nb_dir / "custom.toml").write_text(
        'id = "custom"\nversion = "0.2"\nkind = "regime"\nsummary = "notebook"\n',
        encoding="utf-8",
    )
    assert disciplines.load_discipline("custom").version == "0.1"
    assert disciplines.load_discipline("custom", root).version == "0.2"
    assert disciplines.load_discipline("custom", root).origin == "notebook"


def test_aka_resolution():
    assert disciplines.resolve_discipline_id("screening") == "systematic-screening"
    assert disciplines.resolve_discipline_id("Inclusion Screening") == "systematic-screening"
    assert disciplines.resolve_discipline_id("chain of custody") == "lineage"
    assert disciplines.resolve_discipline_id("no such thing") is None
    assert disciplines.load_discipline("screening").id == "systematic-screening"


# ---------------------------------------------------------------- pins & versions


def test_parse_pin_forms():
    assert disciplines.parse_pin("lineage@1") == ("lineage", 1, None)
    assert disciplines.parse_pin("lineage@1.0") == ("lineage", 1, 0)
    assert disciplines.parse_pin("systematic-screening@0.1") == ("systematic-screening", 0, 1)
    assert disciplines.parse_pin("lineage") is None
    assert disciplines.parse_pin("lineage@") is None
    assert disciplines.parse_pin("Lineage@1") is None
    assert disciplines.parse_pin("") is None


def test_pick_version_bare_major_prefers_highest_minor():
    assert disciplines.pick_version(["1.0", "1.2", "1.1"], 1, None) == "1.2"


def test_pick_version_major_must_match():
    assert disciplines.pick_version(["2.0", "2.3"], 1, None) is None


def test_pick_version_exact_takes_its_minor_or_newer():
    assert disciplines.pick_version(["1.0"], 1, 0) == "1.0"
    assert disciplines.pick_version(["1.2"], 1, 0) == "1.2"  # moved — doctor WARNs
    assert disciplines.pick_version(["1.0"], 1, 2) is None  # older only: no match


def test_resolve_pin_success_and_failures():
    d, reason = disciplines.resolve_pin("lineage@1")
    assert d is not None and reason is None
    assert d.version == "1.1"
    d, reason = disciplines.resolve_pin("no-such@1")
    assert d is None and "no known discipline" in reason
    d, reason = disciplines.resolve_pin("lineage@2")
    assert d is None and "matches no available version" in reason
    d, reason = disciplines.resolve_pin("not a pin")
    assert d is None and "malformed" in reason


# ---------------------------------------------------------------- built-ins


def test_builtin_form_a_codes_are_all_registered():
    for did in ("lineage", "forecasting", "systematic-screening"):
        d = disciplines.load_discipline(did)
        for code in d.claimed_codes():
            assert code in CHECK_CODES, f"{did} references unregistered code {code!r}"
        assert disciplines.validate_discipline(d) == []


def test_lineage_shape():
    d = disciplines.load_discipline("lineage")
    assert [s.id for s in d.slots] == ["custody", "grading", "corroboration", "release"]
    assert all(s.owns for s in d.slots)
    gates = {g.id: g for g in d.gates}
    assert gates["verified-bar"].check == "under-verified"
    assert gates["verified-bar"].slot == "corroboration"
    assert gates["closed-chains"].check == "provenance-open"
    assert all(g.kind == "enforced" for g in d.gates)
    assert d.governs == ["sources", "claims"]
    assert {e["check"] for e in d.checks} == {
        "corroboration-drift", "seeded-grade", "grade-drift", "unaudited-claim",
        "enum-without-evidence", "unlogged-capture", "orphan-provenance", "source-drift", "drifted-evidence"}


def test_forecasting_shape():
    d = disciplines.load_discipline("forecasting")
    assert [s.id for s in d.slots] == ["resolution", "calibration", "two-object"]
    gates = {g.check for g in d.gates}
    assert gates == {"two-object", "undated-forecast", "missing-annul-if"}
    assert {e["check"] for e in d.checks} == {
        "overdue-forecast", "dangling-bears-on", "scored-cluster",
        "impure-inference-link",
    }


def test_systematic_screening_shape():
    d = disciplines.load_discipline("systematic-screening")
    assert d.version == "0.1"  # authored: 0.x by the versioning policy
    assert d.aka == ["screening", "inclusion screening"]
    assert [s.id for s in d.slots] == ["screening"]
    assert d.slots[0].owns is True
    (gate,) = d.gates
    assert gate.kind == "enforced"
    assert isinstance(gate.check, dict)
    assert gate.check["requires"] == "one_of"
    assert gate.check["one_of"] == ["include", "exclude"]
    assert gate.check["class"] == "references"
    (check,) = d.checks
    assert check["field"] == "screening.criterion"
    assert check["requires"] == "present"


def test_validate_flags_unknown_check_code():
    d = disciplines._discipline_from_toml(
        'id = "t"\nversion = "0.1"\nkind = "regime"\n\n'
        '[[gate]]\nid = "g"\nslot = "s"\nkind = "enforced"\ncheck = "no-such-code"\n',
        None, "user",
    )
    problems = disciplines.validate_discipline(d)
    assert any("no-such-code" in p for p in problems)


def test_validate_flags_bad_version_kind_and_predicate():
    d = disciplines._discipline_from_toml(
        'id = "t"\nversion = "1"\nkind = "vibe"\n\n'
        '[[gate]]\nid = "g"\nslot = "s"\nkind = "blocking"\n'
        '[gate.check]\nclass = "nowhere"\nrequires = "sometimes"\n',
        None, "user",
    )
    problems = " | ".join(disciplines.validate_discipline(d))
    assert "MAJOR.MINOR" in problems
    assert "'vibe' invalid" in problems
    assert "'blocking' invalid" in problems
    assert "unknown class 'nowhere'" in problems
    assert "missing 'field'" in problems
    assert "'requires'" in problems


def test_corrections_and_extends_are_parsed_and_carried():
    d = disciplines._discipline_from_toml(
        'id = "t"\nversion = "0.1"\nkind = "regime"\nextends = "lineage"\n\n'
        '[corrections]\npolicy = "retract loudly"\n',
        None, "user",
    )
    assert d.corrections == {"policy": "retract loudly"}
    assert d.extends == "lineage"
    assert disciplines.validate_discipline(d) == []  # carried, never judged


# ---------------------------------------------------------------- dormancy acceptance


def populate(root: Path) -> None:
    """Findings that lineage and forecasting claim: an unlogged source, a
    load-bearing asserted claim with no corroboration, an open forecast with
    no annul_if."""
    (root / "references").mkdir(exist_ok=True)
    pages.write_page(
        root / "references" / "a1.md",
        {"id": "A1", "type": "Source", "aliases": ["A1"]}, "# A1\n",
    )
    (root / "claims").mkdir(exist_ok=True)
    pages.write_page(
        root / "claims" / "c1.md",
        {"id": "C1", "type": "Claim", "aliases": ["C1"], "status": "asserted",
         "load_bearing": True, "description": "the sky is blue"},
        "# C1\n",
    )
    (root / "forecasts").mkdir(exist_ok=True)
    pages.write_page(
        root / "forecasts" / "f1.md",
        {"id": "FC1", "type": "Forecast", "aliases": ["FC1"], "status": "open",
         "resolves_by": "2099-01-01", "description": "it will rain"},
        "# FC1\n",
    )


def test_effective_pins_implicit_set(tmp_path):
    root = make_notebook(tmp_path)
    pins, declared = disciplines.effective_pins(root, [])
    assert pins == ["lineage@1"]
    assert declared is False
    (root / "forecasts").mkdir(exist_ok=True)
    pins, declared = disciplines.effective_pins(root, [])
    assert pins == ["lineage@1", "forecasting@1"]
    assert declared is False
    pins, declared = disciplines.effective_pins(root, ["systematic-screening@0.1"])
    assert pins == ["systematic-screening@0.1"]
    assert declared is True


def test_doctor_byte_identical_when_undeclared(tmp_path):
    """The dormancy rule: with no `disciplines:` key the implicit set adds no
    findings and no labels — doctor output is byte-identical to pre-0.14."""
    root = make_notebook(tmp_path)
    populate(root)
    findings = run_doctor(root)
    assert findings, "the fixture should produce findings to compare"
    for f in findings:
        assert f.code not in DISCIPLINE_CODES
        assert "(lineage)" not in f.message
        assert "(forecasting)" not in f.message
        assert "advisory (" not in f.message
        assert "attested (" not in f.message


def test_doctor_labels_findings_on_explicit_declare(tmp_path):
    """Acceptance (design-composition-0.14.md ship item 1): declaring
    lineage+forecasting yields byte-identical findings, labeled by owner."""
    root = make_notebook(tmp_path)
    populate(root)
    before = run_doctor(root)
    declare(root, ["lineage@1", "forecasting@1"])
    after = run_doctor(root)

    assert [(f.level, f.code, f.path, f.expected) for f in after] == [
        (f.level, f.code, f.path, f.expected) for f in before
    ]
    lineage_codes = disciplines.load_discipline("lineage").claimed_codes()
    forecasting_codes = disciplines.load_discipline("forecasting").claimed_codes()
    labeled = 0
    for b, a in zip(before, after):
        if a.code in lineage_codes:
            assert a.message == f"{b.message} (lineage)"
            labeled += 1
        elif a.code in forecasting_codes:
            assert a.message == f"{b.message} (forecasting)"
            labeled += 1
        else:
            assert a.message == b.message
    assert labeled >= 2  # at least unaudited-claim + missing-annul-if fired


# ---------------------------------------------------------------- doctor: pins & moved


def find(findings, code):
    return [f for f in findings if f.code == code]


def test_unknown_discipline_pin_errors(tmp_path):
    root = make_notebook(tmp_path)
    declare(root, ["no-such@1"])
    (bad,) = find(run_doctor(root), "unknown-discipline")
    assert bad.level == "ERROR"
    assert "no-such@1" in bad.message


def test_malformed_pin_errors(tmp_path):
    root = make_notebook(tmp_path)
    declare(root, ["lineage"])  # no @MAJOR: malformed as a pin
    (bad,) = find(run_doctor(root), "unknown-discipline")
    assert "malformed" in bad.message


def test_discipline_moved_warns_on_exact_pin_with_newer_minor(tmp_path):
    write_user_discipline(
        tmp_path, "lineage",
        (DOCTOR_PY.parent / "disciplines_builtin" / "lineage.toml")
        .read_text(encoding="utf-8")
        .replace('version = "1.0"', 'version = "1.1"'),
    )
    root = make_notebook(tmp_path)
    declare(root, ["lineage@1.0"])
    (moved,) = find(run_doctor(root), "discipline-moved")
    assert moved.level == "WARN"
    assert "lineage@1.1" in moved.message
    # a bare-major pin follows the minor silently — the normal form
    declare(root, ["lineage@1"])
    assert not find(run_doctor(root), "discipline-moved")


def test_bad_discipline_gate_with_unknown_check_errors(tmp_path):
    write_user_discipline(
        tmp_path, "wonky",
        'id = "wonky"\nversion = "0.1"\nkind = "regime"\nsummary = "s"\n\n'
        '[[slot]]\nid = "area"\n\n'
        '[[gate]]\nid = "g"\nslot = "area"\nkind = "enforced"\ncheck = "no-such-code"\n',
    )
    root = make_notebook(tmp_path)
    declare(root, ["wonky@0.1"])
    (bad,) = find(run_doctor(root), "bad-discipline")
    assert bad.level == "ERROR"
    assert "no-such-code" in bad.message


# ---------------------------------------------------------------- doctor: slots


TWO_OWNERS = (
    'id = "{name}"\nversion = "0.1"\nkind = "regime"\nsummary = "s"\n\n'
    '[[slot]]\nid = "{slot}"\n'
)


def test_unresolved_slot_conflict_errors_then_resolves(tmp_path):
    write_user_discipline(tmp_path, "one", TWO_OWNERS.format(name="one", slot="staleness"))
    write_user_discipline(tmp_path, "two", TWO_OWNERS.format(name="two", slot="staleness"))
    root = make_notebook(tmp_path)
    declare(root, ["one@0.1", "two@0.1"])
    (conflict,) = find(run_doctor(root), "unresolved-slot")
    assert conflict.level == "ERROR"
    assert "one, two" in conflict.message
    assert "staleness" in conflict.message

    declare(root, ["one@0.1", "two@0.1"], resolve={"staleness": "two"})
    assert not find(run_doctor(root), "unresolved-slot")


def test_resolution_naming_undeclared_discipline_errors(tmp_path):
    write_user_discipline(tmp_path, "one", TWO_OWNERS.format(name="one", slot="staleness"))
    root = make_notebook(tmp_path)
    declare(root, ["one@0.1"], resolve={"staleness": "ghost"})
    (bad,) = find(run_doctor(root), "unresolved-slot")
    assert "'ghost'" in bad.message
    assert "not declared" in bad.message


def test_non_owning_slot_does_not_conflict(tmp_path):
    write_user_discipline(tmp_path, "one", TWO_OWNERS.format(name="one", slot="staleness"))
    write_user_discipline(
        tmp_path, "two",
        'id = "two"\nversion = "0.1"\nkind = "overlay"\nsummary = "s"\n\n'
        '[[slot]]\nid = "staleness"\nowns = false\n',
    )
    root = make_notebook(tmp_path)
    declare(root, ["one@0.1", "two@0.1"])
    assert not find(run_doctor(root), "unresolved-slot")


def test_depends_on_unmet_warns_and_met_is_silent(tmp_path):
    write_user_discipline(
        tmp_path, "leaning",
        'id = "leaning"\nversion = "0.1"\nkind = "overlay"\nsummary = "s"\n'
        'depends_on = ["lineage@1"]\n',
    )
    root = make_notebook(tmp_path)
    declare(root, ["leaning@0.1"])
    (dep,) = find(run_doctor(root), "discipline-dependency")
    assert dep.level == "WARN"
    assert "lineage@1" in dep.message
    declare(root, ["leaning@0.1", "lineage@1"])
    assert not find(run_doctor(root), "discipline-dependency")


def test_slot_near_miss_advisory(tmp_path):
    write_user_discipline(tmp_path, "one", TWO_OWNERS.format(name="one", slot="sourcing.tier"))
    write_user_discipline(tmp_path, "two", TWO_OWNERS.format(name="two", slot="sourcing-tier"))
    root = make_notebook(tmp_path)
    declare(root, ["one@0.1", "two@0.1"])
    findings = run_doctor(root)
    (miss,) = find(findings, "slot-name-mismatch")
    assert miss.level == "WARN"
    assert "'sourcing-tier' (two)" in miss.message
    assert "'sourcing.tier' (one)" in miss.message
    assert not find(findings, "unresolved-slot")  # spelled apart: never collides


# ---------------------------------------------------------------- field predicates


SCREENED = (
    'id = "screener"\nversion = "0.1"\nkind = "regime"\nsummary = "s"\n\n'
    '[[slot]]\nid = "screening"\n\n'
    '[[gate]]\nid = "typed-decision"\nslot = "screening"\nkind = "{gate_kind}"\n'
    '[gate.check]\nclass = "references"\nfield = "screening.decision"\n'
    'requires = "one_of"\none_of = ["include", "exclude"]\nmessage = "screened sources say why"\n'
)


def add_source_page(root: Path, sid: str, fm_extra: dict | None = None) -> None:
    (root / "references").mkdir(exist_ok=True)
    fm = {"id": sid, "type": "Source", "aliases": [sid]}
    fm.update(fm_extra or {})
    pages.write_page(root / "references" / f"{sid.lower()}.md", fm, f"# {sid}\n")


def test_predicate_one_of_owner_errors_and_passes(tmp_path):
    write_user_discipline(tmp_path, "screener", SCREENED.format(gate_kind="enforced"))
    root = make_notebook(tmp_path)
    add_source_page(root, "A1")  # no screening.decision at all
    add_source_page(root, "A2", {"screening": {"decision": "maybe"}})
    add_source_page(root, "A3", {"screening": {"decision": "include"}})
    declare(root, ["screener@0.1"])
    hits = find(run_doctor(root), "typed-decision")
    assert len(hits) == 2
    assert all(h.level == "ERROR" for h in hits)
    assert all("(screener)" in h.message for h in hits)
    assert any("missing or empty" in h.message for h in hits)
    assert any("'maybe' (one of: include, exclude)" in h.message for h in hits)
    assert all("screened sources say why" in h.message for h in hits)


def test_predicate_present_and_absent(tmp_path):
    write_user_discipline(
        tmp_path, "fields",
        'id = "fields"\nversion = "0.1"\nkind = "regime"\nsummary = "s"\n\n'
        '[[slot]]\nid = "area"\n\n'
        '[[gate]]\nid = "needs-basis"\nslot = "area"\nkind = "enforced"\n'
        '[gate.check]\nclass = "references"\nfield = "support.basis"\nrequires = "present"\n'
        'message = "say the basis"\n\n'
        '[[gate]]\nid = "no-legacy"\nslot = "area"\nkind = "enforced"\n'
        '[gate.check]\nclass = "references"\nfield = "legacy_note"\nrequires = "absent"\n'
        'message = "legacy_note is retired"\n',
    )
    root = make_notebook(tmp_path)
    add_source_page(root, "A1", {"support": {"basis": "official-record"}, "legacy_note": "x"})
    add_source_page(root, "A2")
    declare(root, ["fields@0.1"])
    findings = run_doctor(root)
    (basis,) = find(findings, "needs-basis")
    assert "A2" in basis.message and basis.level == "ERROR"
    (legacy,) = find(findings, "no-legacy")
    assert "A1" in legacy.message and "must be absent" in legacy.message


def test_non_owner_predicate_is_labeled_advisory_warn(tmp_path):
    write_user_discipline(tmp_path, "one", TWO_OWNERS.format(name="one", slot="screening"))
    write_user_discipline(tmp_path, "screener", SCREENED.format(gate_kind="enforced"))
    root = make_notebook(tmp_path)
    add_source_page(root, "A1")
    # both own screening; the manifest resolves to "one", so screener's
    # enforced gate demotes to a labeled advisory (union-the-rubrics rule)
    declare(root, ["one@0.1", "screener@0.1"], resolve={"screening": "one"})
    (hit,) = find(run_doctor(root), "typed-decision")
    assert hit.level == "WARN"
    assert hit.message.startswith("advisory (screener): ")
    assert hit.expected is False


def test_attested_gate_never_errors(tmp_path):
    write_user_discipline(tmp_path, "screener", SCREENED.format(gate_kind="attested"))
    root = make_notebook(tmp_path)
    add_source_page(root, "A1")
    declare(root, ["screener@0.1"])
    (hit,) = find(run_doctor(root), "typed-decision")
    assert hit.level == "WARN"
    assert hit.expected is True
    assert hit.message.startswith("attested (screener): recorded, not enforced — ")
    # and a passing corpus stays silent
    add_source_page(root, "A1", {"screening": {"decision": "include"}})
    assert not find(run_doctor(root), "typed-decision")


def test_advisory_check_predicate_warns(tmp_path):
    root = make_notebook(tmp_path)
    add_source_page(root, "A1", {"screening": {"decision": "include"}})
    declare(root, ["systematic-screening@0.1"])
    findings = run_doctor(root)
    assert not find(findings, "typed-screening-decision")  # gate satisfied
    (crit,) = find(findings, "screening-criterion-stated")
    assert crit.level == "WARN"
    assert crit.message.startswith("advisory (systematic-screening): ")
    assert "screening.criterion" in crit.message


# ---------------------------------------------------------------- kind requires


def test_kind_requires_parsed_on_lit_review():
    k = kinds.load_kind("lit-review")
    assert k.requires == [{"slot": "screening", "default": "systematic-screening@0.1"}]


def test_slot_unfilled_when_declared_without_owner(tmp_path):
    root = make_notebook(tmp_path, kind="scout")
    kinds.adopt_kind(root, "lit-review")
    declare(root, ["lineage@1"])
    (gap,) = find(run_doctor(root), "slot-unfilled")
    assert gap.level == "ERROR"
    assert "'screening'" in gap.message
    assert "systematic-screening@0.1" in gap.message  # the default, named as the fix


def test_kind_requires_informational_when_undeclared(tmp_path):
    root = make_notebook(tmp_path, kind="scout")
    kinds.adopt_kind(root, "lit-review")
    assert not find(run_doctor(root), "slot-unfilled")


def test_slot_unfilled_clears_when_default_declared(tmp_path):
    root = make_notebook(tmp_path, kind="scout")
    kinds.adopt_kind(root, "lit-review")
    declare(root, ["lineage@1", "systematic-screening@0.1"])
    assert not find(run_doctor(root), "slot-unfilled")


# ---------------------------------------------------------------- manifest & export


def test_manifest_round_trips_disciplines(tmp_path):
    root = make_notebook(tmp_path)
    declare(root, ["lineage@1", "forecasting@1"], resolve={"release": "lineage"})
    m = load_manifest(root)
    assert m.disciplines == ["lineage@1", "forecasting@1"]
    assert m.discipline_resolve == {"release": "lineage"}
    save_manifest(root, m)  # a second save keeps them (not eaten by extras)
    m2 = load_manifest(root)
    assert m2.disciplines == ["lineage@1", "forecasting@1"]
    assert m2.discipline_resolve == {"release": "lineage"}
    assert "disciplines" not in m2.extras


def test_render2_notebook_block_carries_declared_disciplines(tmp_path):
    root = make_notebook(tmp_path)
    v2 = export_json(root, include_private=True, render_version=2)
    assert "disciplines" not in v2["notebook"]  # nothing declared: absent
    declare(root, ["lineage@1"])
    v2 = export_json(root, include_private=True, render_version=2)
    assert v2["notebook"]["disciplines"] == ["lineage@1"]
    v1 = export_json(root, include_private=True, render_version=1)
    assert "disciplines" not in v1["notebook"]  # render/1 stays byte-stable


def test_export_okf_manifest_passthrough_carries_disciplines(tmp_path):
    from flip.okf import export_okf

    root = make_notebook(tmp_path)
    declare(root, ["lineage@1"])
    m = load_manifest(root)
    m.visibility = "public"
    save_manifest(root, m)
    dest = tmp_path / "out"
    export_okf(root, dest)
    fm = pages.read_page(dest / "index.md").fm
    assert fm["disciplines"] == ["lineage@1"]


# ---------------------------------------------------------------- CLI wiring


def test_cli_discipline_list_shows_pins_kind_origin_and_aka():
    result = invoke(["discipline", "list"])
    assert result.exit_code == 0, result.output
    assert "lineage@1.1" in result.output
    assert "forecasting@1.0" in result.output
    assert "systematic-screening@0.1" in result.output
    assert "regime" in result.output
    assert "built-in" in result.output
    assert "aka: screening, inclusion screening" in result.output


def test_cli_discipline_list_json():
    result = invoke(["discipline", "list", "--json"])
    assert result.exit_code == 0, result.output
    rows = {r["id"]: r for r in json.loads(result.output)}
    assert rows["lineage"]["version"] == "1.1"
    assert rows["systematic-screening"]["aka"] == ["screening", "inclusion screening"]


def test_cli_discipline_show_prints_slots_gates_checks():
    result = invoke(["discipline", "show", "lineage"])
    assert result.exit_code == 0, result.output
    assert "lineage@1.1 · regime · built-in" in result.output
    assert "corroboration" in result.output
    assert "verified-bar @ corroboration · enforced · check under-verified" in result.output
    assert "check corroboration-drift" in result.output


def test_cli_discipline_show_predicate_gate_readably():
    result = invoke(["discipline", "show", "systematic-screening"])
    assert result.exit_code == 0, result.output
    assert (
        "typed-screening-decision @ screening · enforced · "
        "references.screening.decision one_of [include, exclude]"
    ) in result.output
    assert "screening-criterion-stated" in result.output


def test_cli_discipline_show_json():
    result = invoke(["discipline", "show", "systematic-screening", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["slots"] == [{"id": "screening", "owns": True}]
    assert data["gates"][0]["check"]["one_of"] == ["include", "exclude"]


def test_cli_discipline_show_unknown_is_actionable():
    result = invoke(["discipline", "show", "no-such"])
    assert result.exit_code == 1
    assert "unknown discipline" in result.output
    assert "lineage" in result.output


def test_cli_discipline_new_scaffolds_and_parses(tmp_path, monkeypatch):
    result = invoke(["discipline", "new", "peer-review"])
    assert result.exit_code == 0, result.output
    path = tmp_path / "fliphome" / "disciplines" / "peer-review.toml"
    assert path.is_file()
    assert str(path) in result.output
    assert "flip discipline show peer-review" in result.output
    d = disciplines.load_discipline("peer-review")
    assert d.id == "peer-review"
    assert d.version == "0.1"  # authored disciplines start at 0.x by policy
    assert d.slots and d.gates
    assert disciplines.validate_discipline(d) == []
    text = path.read_text(encoding="utf-8")
    assert "1.x is reserved" in text  # the template teaches the versioning rule


def test_scaffold_discipline_refuses_existing_without_force():
    disciplines.scaffold_discipline("dup")
    with pytest.raises(SystemExit, match="already exists"):
        disciplines.scaffold_discipline("dup")
    disciplines.scaffold_discipline("dup", force=True)  # does not raise


def test_scaffold_discipline_invalid_id_refused():
    with pytest.raises(SystemExit, match="invalid discipline id"):
        disciplines.scaffold_discipline("Not Valid!")


def test_cli_kind_show_prints_requires():
    result = invoke(["kind", "show", "lit-review"])
    assert result.exit_code == 0, result.output
    assert "slot 'screening' (default: systematic-screening@0.1)" in result.output


# ---------------------------------------------------------------- CHECK_CODES


def test_check_codes_is_complete():
    """Every literal finding code passed to _error/_warn in doctor.py is in
    CHECK_CODES — the registry can't drift from the call sites."""
    tree = ast.parse(DOCTOR_PY.read_text(encoding="utf-8"))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", getattr(node.func, "attr", ""))
        if name in ("_error", "_warn") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                literals.add(first.value)
    assert literals, "expected _error/_warn call sites in doctor.py"
    missing = literals - CHECK_CODES
    assert not missing, f"codes emitted but not registered in CHECK_CODES: {sorted(missing)}"


def test_check_codes_shape():
    assert isinstance(CHECK_CODES, frozenset)
    for code in ("under-verified", "two-object", "provenance-open",
                 "undated-forecast", "missing-annul-if", *DISCIPLINE_CODES):
        assert code in CHECK_CODES
