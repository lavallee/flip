"""Tests for flip.kinds — the Phase 1 outcome-kind registry (design-outcome-kinds.md).

Loader precedence, single-file/directory equivalence, the built-in kinds'
contract shape, adopt's manifest + log side effects, the gap-manifest's
three-tier honesty vocabulary, doctor's kind-gap integration, `flip kind new`'s
scaffold, and the profiles-as-kinds bridge.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import kinds, pages, profiles as profiles_mod, scaffold
from flip.cli import main
from flip.doctor import run_doctor
from flip.manifest import load_manifest
from flip.util import read_jsonl


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(tmp_path: Path, kind: str = "scout", slug: str = "demo") -> Path:
    return scaffold.create_notebook(tmp_path / slug, slug, kind)


# ---------------------------------------------------------------- loader / precedence


def test_list_kinds_includes_builtins_and_profiles():
    rows = {k.id: k for k in kinds.list_kinds()}
    assert rows["lit-review"].origin == "built-in"
    assert rows["decision-packet"].origin == "built-in"
    for pid in profiles_mod.list_profiles():
        assert rows[pid].origin == "profile"
        assert rows[pid].contract == []  # rigor-shaped kinds carry no contract


def test_load_kind_unknown_lists_known_ids():
    with pytest.raises(SystemExit) as exc:
        kinds.load_kind("no-such-kind")
    assert "unknown kind" in str(exc.value)
    assert "lit-review" in str(exc.value)


def test_kind_exists():
    assert kinds.kind_exists("lit-review")
    assert kinds.kind_exists("scout")  # profile-adapter counts too
    assert not kinds.kind_exists("no-such-kind")


def test_user_dir_single_file_and_directory_form_are_equivalent(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    (user_kinds).mkdir(parents=True)
    single = (
        'id = "single-form"\nversion = "0.1"\nsummary = "single file"\n\n'
        '[[contract.require]]\nid = "r1"\nwhat = "a thing"\nentity = "references"\n'
        'assembled_by = "some-render"\n'
    )
    (user_kinds / "single-form.toml").write_text(single, encoding="utf-8")
    dir_form = user_kinds / "dir-form"
    dir_form.mkdir()
    (dir_form / "kind.toml").write_text(
        single.replace('"single-form"', '"dir-form"').replace("single file", "dir file"),
        encoding="utf-8",
    )
    k1 = kinds.load_kind("single-form")
    k2 = kinds.load_kind("dir-form")
    assert k1.origin == k2.origin == "user"
    assert [r.id for r in k1.contract] == [r.id for r in k2.contract]
    assert k1.contract[0].assembled_by == k2.contract[0].assembled_by == "some-render"


def test_kind_contract_may_require_commissions(tmp_path, monkeypatch):
    # commissions/ is a first-class entity dir; a kind can demand contracts
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    user_kinds.mkdir(parents=True)
    (user_kinds / "chained.toml").write_text(
        'id = "chained"\nversion = "0.1"\nsummary = "commissioned follow-ups"\n\n'
        '[[contract.require]]\nid = "k1"\nwhat = "a commission contract"\n'
        'entity = "commissions"\nassembled_by = "the continuation section"\n',
        encoding="utf-8",
    )
    k = kinds.load_kind("chained")
    assert k.contract[0].entity == "commissions"


def test_precedence_user_overrides_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    user_kinds.mkdir(parents=True)
    (user_kinds / "lit-review.toml").write_text(
        'id = "lit-review"\nversion = "9.9"\nsummary = "overridden"\n', encoding="utf-8"
    )
    k = kinds.load_kind("lit-review")
    assert k.version == "9.9"
    assert k.origin == "user"


def test_precedence_notebook_overrides_user(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    user_kinds.mkdir(parents=True)
    (user_kinds / "custom.toml").write_text(
        'id = "custom"\nversion = "0.1"\nsummary = "user level"\n', encoding="utf-8"
    )
    root = tmp_path / "nb"
    nb_kinds = root / ".flip" / "kinds"
    nb_kinds.mkdir(parents=True)
    (nb_kinds / "custom.toml").write_text(
        'id = "custom"\nversion = "0.2"\nsummary = "notebook level"\n', encoding="utf-8"
    )
    assert kinds.load_kind("custom").version == "0.1"  # no root: only user dir visible
    assert kinds.load_kind("custom", root).version == "0.2"  # notebook wins


# ---------------------------------------------------------------- built-ins


@pytest.mark.parametrize("kind_id", ["lit-review", "decision-packet"])
def test_builtin_kinds_parse_and_every_requirement_has_assembled_by(kind_id):
    k = kinds.load_kind(kind_id)
    assert k.origin == "built-in"
    assert k.version
    assert k.summary
    assert k.contract, f"{kind_id} should ship with a non-empty contract"
    for req in k.contract:
        assert req.assembled_by, f"{kind_id}: requirement {req.id!r} has no assembled_by"
        assert req.what
        assert req.entity in kinds.ENTITY_KINDS


def test_lit_review_has_one_prospective_requirement():
    k = kinds.load_kind("lit-review")
    prospective = [r for r in k.contract if r.prospective]
    assert len(prospective) == 1
    assert prospective[0].id == "frozen-criteria"


def test_decision_packet_versioning_is_one_shot():
    k = kinds.load_kind("decision-packet")
    assert k.versioning["mode"] == "one-shot"


def test_field_shorthand_infers_entity_from_first_segment():
    k = kinds._kind_from_toml(
        'id = "t"\nversion = "0.1"\nsummary = "s"\n\n'
        '[[contract.require]]\nid = "r1"\nwhat = "w"\n'
        'field = "references.support.basis"\nassembled_by = "x"\n',
        None, "user",
    )
    req = k.contract[0]
    assert req.entity == "references"
    assert req.field == "support.basis"


def test_missing_assembled_by_is_refused():
    with pytest.raises(SystemExit, match="assembled_by"):
        kinds._kind_from_toml(
            'id = "t"\nversion = "0.1"\nsummary = "s"\n\n'
            '[[contract.require]]\nid = "r1"\nwhat = "w"\nentity = "references"\n',
            None, "user",
        )


# ---------------------------------------------------------------- gap manifest tiers


def _req(**kw) -> kinds.ContractRequirement:
    base = dict(id="r", what="w", assembled_by="x")
    base.update(kw)
    return kinds.ContractRequirement(**base)


def test_gap_manifest_met(tmp_path):
    (tmp_path / "references").mkdir()
    pages.write_page(
        tmp_path / "references" / "a1.md",
        {"id": "A1", "type": "Source", "support": {"basis": "official-record"}}, "# A1\n",
    )
    k = kinds.Kind(id="t", contract=[_req(entity="references", field="support.basis")])
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].tier == "met"
    assert rows[0].have == 1


def test_gap_manifest_recoverable_when_nothing_exists_yet(tmp_path):
    k = kinds.Kind(id="t", contract=[_req(entity="files", path="search-log.md")])
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].tier == "recoverable"
    assert rows[0].have == 0


def test_gap_manifest_reconstructible_with_loss_when_pages_exist_without_field(tmp_path):
    (tmp_path / "references").mkdir()
    pages.write_page(
        tmp_path / "references" / "a1.md", {"id": "A1", "type": "Source"}, "# A1\n"
    )
    k = kinds.Kind(id="t", contract=[_req(entity="references", field="screening.decision")])
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].tier == "reconstructible-with-loss"


def test_gap_manifest_unrecoverable_by_construction_when_prospective(tmp_path):
    k = kinds.Kind(
        id="t",
        contract=[_req(entity="files", path="criteria.md", prospective=True)],
    )
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].tier == "unrecoverable-by-construction"


def test_gap_manifest_prospective_takes_priority_over_reconstructible(tmp_path):
    # Even when pages already exist without the field, a prospective
    # requirement is unrecoverable, never merely reconstructible-with-loss.
    (tmp_path / "references").mkdir()
    pages.write_page(
        tmp_path / "references" / "a1.md", {"id": "A1", "type": "Source"}, "# A1\n"
    )
    k = kinds.Kind(
        id="t",
        contract=[_req(entity="references", field="x.y", prospective=True)],
    )
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].tier == "unrecoverable-by-construction"


def test_gap_manifest_files_glob(tmp_path):
    (tmp_path / "search-log").mkdir()
    (tmp_path / "search-log" / "one.md").write_text("x", encoding="utf-8")
    k = kinds.Kind(id="t", contract=[_req(entity="files", path="search-log/*.md")])
    rows = kinds.gap_manifest(tmp_path, k)
    assert rows[0].have == 1
    assert rows[0].tier == "met"


def test_lit_review_gap_manifest_on_a_fresh_notebook_shows_only_prospective_gap(tmp_path):
    # Acceptance test (d): adopting late loses nothing capture-time discipline
    # could have saved — only the genuinely-prospective gap should be
    # unrecoverable; everything else is still addable.
    root = make_notebook(tmp_path, kind="scout")
    k = kinds.load_kind("lit-review", root)
    rows = kinds.gap_manifest(root, k)
    tiers = {r.requirement_id: r.tier for r in rows}
    assert tiers["frozen-criteria"] == "unrecoverable-by-construction"
    assert tiers["per-source-screening"] == "recoverable"
    assert tiers["extraction-fields"] == "recoverable"
    assert tiers["search-strategy-log"] == "recoverable"


# ---------------------------------------------------------------- adopt


def test_adopt_writes_manifest_and_log_event(tmp_path):
    root = make_notebook(tmp_path)
    k, rows = kinds.adopt_kind(root, "decision-packet")
    assert k.id == "decision-packet"
    m = load_manifest(root)
    assert m.kind == "decision-packet"
    assert m.visibility == "client-confidential"  # applied from [defaults]
    log_rows = read_jsonl(root / "log" / "log.jsonl")
    assert any(r.get("text") == "kind-adopt decision-packet" for r in log_rows)
    assert any(r.get("actor") for r in log_rows)
    assert len(rows) == 4  # decision-packet ships four contract requirements


def test_adopt_unknown_kind_refuses(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit, match="unknown kind"):
        kinds.adopt_kind(root, "no-such-kind")
    # refusing must not have touched the manifest
    assert load_manifest(root).kind == "scout"


def test_adopt_kind_with_no_contract_is_a_no_op_gap_check(tmp_path):
    root = make_notebook(tmp_path, kind="scout")
    _k, rows = kinds.adopt_kind(root, "ledger")  # a profile-adapter kind
    assert rows == []
    assert load_manifest(root).kind == "ledger"


# ---------------------------------------------------------------- doctor integration


def test_doctor_kind_gap_warns_while_active_and_errors_when_done(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    user_kinds.mkdir(parents=True)
    (user_kinds / "gappy.toml").write_text(
        'id = "gappy"\nversion = "0.1"\nsummary = "s"\n\n'
        '[[contract.require]]\nid = "needs-file"\nwhat = "a required file"\n'
        'entity = "files"\npath = "criteria.md"\nassembled_by = "review"\n',
        encoding="utf-8",
    )
    root = make_notebook(tmp_path, kind="scout", slug="nb")
    kinds.adopt_kind(root, "gappy")

    findings = run_doctor(root)
    gap = [f for f in findings if f.code == "kind-gap"]
    assert len(gap) == 1
    assert gap[0].level == "WARN"
    assert gap[0].expected is True

    m = load_manifest(root)
    m.status = "done"
    from flip.manifest import save_manifest

    save_manifest(root, m)
    findings = run_doctor(root)
    gap = [f for f in findings if f.code == "kind-gap"]
    assert len(gap) == 1
    assert gap[0].level == "ERROR"


def test_doctor_kind_gap_is_a_no_op_for_profile_kinds(tmp_path):
    root = make_notebook(tmp_path, kind="scout")
    findings = run_doctor(root)
    assert not [f for f in findings if f.code == "kind-gap"]


def test_doctor_kind_gap_clears_once_requirement_met(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    user_kinds = tmp_path / "fliphome" / "kinds"
    user_kinds.mkdir(parents=True)
    (user_kinds / "gappy.toml").write_text(
        'id = "gappy"\nversion = "0.1"\nsummary = "s"\n\n'
        '[[contract.require]]\nid = "needs-file"\nwhat = "a required file"\n'
        'entity = "files"\npath = "criteria.md"\nassembled_by = "review"\n',
        encoding="utf-8",
    )
    root = make_notebook(tmp_path, kind="scout", slug="nb")
    kinds.adopt_kind(root, "gappy")
    (root / "criteria.md").write_text("frozen\n", encoding="utf-8")
    findings = run_doctor(root)
    assert not [f for f in findings if f.code == "kind-gap"]


# ---------------------------------------------------------------- flip kind new


def test_scaffold_kind_writes_template_that_parses(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    path = kinds.scaffold_kind("my-new-kind")
    assert path == tmp_path / "fliphome" / "kinds" / "my-new-kind.toml"
    k = kinds.load_kind("my-new-kind")
    assert k.id == "my-new-kind"
    assert k.version == "0.1"
    assert len(k.contract) == 1
    assert k.contract[0].assembled_by


def test_scaffold_kind_refuses_existing_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    kinds.scaffold_kind("dup")
    with pytest.raises(SystemExit, match="already exists"):
        kinds.scaffold_kind("dup")
    kinds.scaffold_kind("dup", force=True)  # does not raise


def test_scaffold_kind_invalid_id_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    with pytest.raises(SystemExit, match="invalid kind id"):
        kinds.scaffold_kind("Not Valid!")


# ---------------------------------------------------------------- CLI wiring


def test_cli_kind_list_shows_builtins_and_profiles():
    result = invoke(["kind", "list"])
    assert result.exit_code == 0, result.output
    assert "lit-review" in result.output
    assert "decision-packet" in result.output
    assert "scout" in result.output


def test_cli_kind_show_unknown_is_actionable():
    result = invoke(["kind", "show", "no-such-kind"])
    assert result.exit_code == 1
    assert "unknown kind" in result.output
    assert "lit-review" in result.output


def test_cli_kind_show_lists_contract_and_assembled_by():
    result = invoke(["kind", "show", "lit-review"])
    assert result.exit_code == 0, result.output
    assert "frozen-criteria" in result.output
    assert "assembled by" in result.output
    assert "[prospective]" in result.output


def test_cli_new_with_kind_scout_still_works(tmp_path, monkeypatch):
    # kinds.py must be additive: `flip new --kind scout` keeps its existing
    # profile-only path untouched.
    monkeypatch.chdir(tmp_path)
    result = invoke(["new", "demo", "--kind", "scout"])
    assert result.exit_code == 0, result.output
    assert load_manifest(tmp_path / "demo").kind == "scout"


def test_cli_kind_adopt_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["new", "demo", "--kind", "scout"])
    assert result.exit_code == 0, result.output
    root = tmp_path / "demo"
    result = invoke(["--notebook", str(root), "kind", "adopt", "lit-review"])
    assert result.exit_code == 0, result.output
    assert "kind -> lit-review" in result.output
    assert "gap manifest" in result.output
    assert "unrecoverable-by-construction" in result.output
    assert load_manifest(root).kind == "lit-review"
    log_rows = read_jsonl(root / "log" / "log.jsonl")
    assert any(r.get("text") == "kind-adopt lit-review" for r in log_rows)


def test_cli_kind_adopt_unknown_refuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    invoke(["new", "demo", "--kind", "scout"])
    root = tmp_path / "demo"
    result = invoke(["--notebook", str(root), "kind", "adopt", "no-such-kind"])
    assert result.exit_code == 1
    assert "unknown kind" in result.output


def test_cli_kind_new_scaffolds_and_prints_next_step(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    result = invoke(["kind", "new", "swot-brief"])
    assert result.exit_code == 0, result.output
    path = tmp_path / "fliphome" / "kinds" / "swot-brief.toml"
    assert path.is_file()
    assert str(path) in result.output
    assert "flip kind show swot-brief" in result.output


# --- aka resolution (outcome-mode translation) --------------------------------


def test_resolve_kind_id_matches_ids_and_aka_normalized():
    assert kinds.resolve_kind_id("lit-review") == "lit-review"
    assert kinds.resolve_kind_id("Literature Review") == "lit-review"
    assert kinds.resolve_kind_id("systematic_review") == "lit-review"
    assert kinds.resolve_kind_id("due diligence") == "decision-packet"
    assert kinds.resolve_kind_id("quick look") == "scout"
    assert kinds.resolve_kind_id("no such outcome") is None
    assert kinds.resolve_kind_id("") is None


def test_load_kind_accepts_aka_phrases():
    k = kinds.load_kind("evidence review")
    assert k.id == "lit-review"


def test_load_kind_refusal_mentions_plain_language(tmp_path):
    with pytest.raises(SystemExit) as exc:
        kinds.load_kind("interpretive dance")
    assert "plain-language" in str(exc.value)


def test_builtin_kinds_declare_aka():
    for kid in ("lit-review", "decision-packet"):
        assert kinds.load_kind(kid).aka, f"{kid} should carry aka phrases"


def test_new_cli_canonicalizes_aka(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from click.testing import CliRunner
    from flip.cli import main as cli_main
    result = CliRunner().invoke(cli_main, ["new", "sr", "--kind", "Systematic Review",
                                           "--title", "t"])
    assert result.exit_code == 0, result.output
    assert "created lit-review notebook" in result.output
    fm = pages.read_page(tmp_path / "sr" / "index.md").fm
    assert fm["kind"] == "lit-review"
