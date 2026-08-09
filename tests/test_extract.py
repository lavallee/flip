"""Tests for the `[extractors]` lane — text derivatives of raw custody (SPEC §5.5).

`sources/text/` has been in the spec since the beginning and nothing ever wrote
it; `derived/_derivations.jsonl` was specified and unused. These tests are about
the two things that makes possible and the two ways it could go wrong quietly:

  - a notebook can finally SAY how a quotation was recovered — text layer or
    OCR — which is a difference in what the evidence is worth, not a detail;
  - an extraction that produced nothing, or nearly nothing, is caught at
    extraction time rather than after it has been cited.

No extractor is installed to run these. flip's contract with the role is a
command template and three placeholders, so a four-line shell script is a
conformant extractor and is exactly what the fixtures use — the same way
test_integrations.py fakes fetchers.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import doctor, integrations, sources
from flip.cli import main
from flip.util import read_jsonl, sha256_file

ROOT_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: extract-nb
kind: scout
status: active
created: 2026-01-01
updated: 2026-01-01
---
# extract-nb
"""

# A PDF-shaped fixture: real enough for `page_count`'s crude object scan, which
# is all the words-per-page test needs. Three `/Type /Page` leaves, one `/Pages`
# tree node → 3 pages.
PDF_3PAGE = b"%PDF-1.4\n" + b"/Type /Page\n" * 3 + b"/Type /Pages\n"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    nb = tmp_path / "nb"
    nb.mkdir()
    (nb / "index.md").write_text(ROOT_MD, encoding="utf-8")
    return nb.resolve()


def make_script(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / name
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def set_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toml_text: str) -> Path:
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(toml_text, encoding="utf-8")
    monkeypatch.setenv("FLIP_HOME", str(home))
    return home


def capture(root: Path, source_id: str, body: bytes = PDF_3PAGE, suffix: str = ".pdf") -> Path:
    """Put bytes into custody the way `builtin:copy` does, without running one."""
    raw = root / "sources" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / f"{source_id}{suffix}"
    path.write_bytes(body)
    return path


def words_script(tmp_path: Path, count: int, name: str = "goodext") -> Path:
    """An extractor that writes `count` words to {out} — a lane that works."""
    return make_script(
        tmp_path, name,
        f'awk \'BEGIN{{for(i=0;i<{count};i++) printf "word%d ", i}}\' > "$2"\n',
    )


# --- the role exists at all -------------------------------------------------


def test_extractors_is_a_role_so_the_table_is_not_silently_ignored():
    """Without `extractors` in ROLES, an operator's [extractors] table parses
    fine and does nothing: `flip config show` skips it and every error message
    pretends the lane was never written. A role that reads as absent when it is
    present is the worst of the three states."""
    assert "extractors" in integrations.ROLES
    assert integrations._ROLE_TOOL["extractors"] == "your-extractor"


def test_unconfigured_lane_names_the_operators_file_and_ships_no_default(
    tmp_path, monkeypatch
):
    """flip bundles `flip-fetch` because it is stdlib-only. A PDF extractor is
    not, and flip must not acquire an opinion about PDF libraries inside its own
    package (§16) — so the error hands back a stanza and stops, and says so."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "nothing"))
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("extractors", "pdf")
    msg = str(ei.value)
    assert "[extractors]" in msg
    assert 'pdf = "your-extractor {src} {out}"' in msg
    assert "flip ships no extractor" in msg
    assert "{out} the destination text file, omit it and stdout is captured" in msg


def test_starter_config_offers_extractors_but_configures_none(tmp_path, monkeypatch):
    """The starter config's [extractors] block is entirely commented. A default
    lane would be flip picking a PDF library for every deployment; a commented
    one is a place to start with the operator still choosing."""
    import tomllib

    data = tomllib.loads(integrations.STARTER_CONFIG)
    assert "extractors" not in data
    assert "[extractors]" in integrations.STARTER_CONFIG
    assert "{src}" in integrations.STARTER_CONFIG and "{out}" in integrations.STARTER_CONFIG


# --- run_extraction: the runner, and the {out} rule -------------------------


def test_stdout_is_preserved_when_the_template_omits_out(root, tmp_path, monkeypatch):
    """Exactly `{dest}`'s rule in run_capture, one layer down: a tool that
    writes a file gets `{out}`; a tool that prints to stdout omits it and flip
    catches what it printed. Requiring every extractor to take an output path
    would exclude most of the ones that exist."""
    tool = make_script(tmp_path, "stdoutext", 'printf "alpha beta gamma"\n')
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}}"\n')
    src = capture(root, "F1")
    run = integrations.run_extraction(
        integrations.resolve("extractors", "pdf"), root, "F1",
        src, root / "sources" / "text" / "F1.txt",
    )
    assert run.captures_stdout is True
    assert run.words == 3
    assert (root / "sources" / "text" / "F1.txt").read_text() == "alpha beta gamma"


def test_a_clean_run_with_no_text_is_an_empty_extraction_not_a_failure(
    root, tmp_path, monkeypatch
):
    """An extractor that exits 0 having found no words has reported a finding
    ABOUT THE DOCUMENT — this scan has no text layer — not a defect in the
    config. Calling it a failure sends the reader to debug a lane that is fine,
    and the predictable next move is a hand-rolled render-and-recognize loop
    with no derivation row behind the words it produces."""
    tool = make_script(tmp_path, "silent", "exit 0\n")
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = capture(root, "F1")
    with pytest.raises(integrations.EmptyExtraction) as ei:
        integrations.run_extraction(
            integrations.resolve("extractors", "pdf"), root, "F1",
            src, root / "sources" / "text" / "F1.txt",
        )
    exc = ei.value
    assert isinstance(exc, SystemExit)          # every caller behaves as before
    assert exc.key == "pdf" and exc.tool == str(tool)
    assert "ran clean (exit 0)" in str(exc)
    assert "produced no text" in str(exc)
    # and nothing is left on disk: a zero-byte .txt is the one artifact that
    # would read, later, exactly like a successful extraction
    assert not (root / "sources" / "text" / "F1.txt").exists()


def test_a_nonzero_exit_stays_an_ordinary_failure(root, tmp_path, monkeypatch):
    """The distinction only means anything if the other side keeps its shape."""
    tool = make_script(tmp_path, "brokenext", 'echo "libpoppler missing" >&2\nexit 3\n')
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = capture(root, "F1")
    with pytest.raises(SystemExit) as ei:
        integrations.run_extraction(
            integrations.resolve("extractors", "pdf"), root, "F1",
            src, root / "sources" / "text" / "F1.txt",
        )
    assert not isinstance(ei.value, integrations.EmptyExtraction)
    assert "exit 3" in str(ei.value) and "libpoppler missing" in str(ei.value)


def test_a_tool_that_promises_out_and_writes_nothing_cannot_pass_off_the_old_file(
    root, tmp_path, monkeypatch
):
    """The failure this lane exists to catch, in its purest form.

    A template naming `{out}` promises to write it. When such a tool exits 0 and
    writes nothing, the PREVIOUS derivative is still sitting at that path — and
    reading it back would produce a fresh derivation row, a fresh timestamp, and
    last week's words presented as this run's output. run_capture only counts
    files that were not in {dest} before; this is the same discipline.
    """
    good = words_script(tmp_path, 600)
    silent = make_script(tmp_path, "silent", "exit 0\n")
    set_config(
        tmp_path, monkeypatch,
        f'[extractors.pdf]\ndefault = "{good} {{src}} {{out}}"\n'
        f'silent = "{silent} {{src}} {{out}}"\n',
    )
    capture(root, "F1")
    first = sources.extract_text(root, "F1", method="text-layer")
    assert first["outputs"][0]["words"] == 600

    with pytest.raises(integrations.EmptyExtraction):
        sources.extract_text(root, "F1", via="silent")
    # the earlier, real derivative is restored rather than destroyed or reused
    assert (root / "sources" / "text" / "F1.txt").read_text().startswith("word0 ")
    rows = read_jsonl(root / sources.DERIVATIONS)
    assert rows[-1]["status"] == "not-extracted"
    assert "outputs" not in rows[-1]


# --- derivative_fidelity: derived from the row, never authored --------------


def test_fidelity_is_derived_from_words_and_pages():
    """25 words/page is not a guess. Measured genuine extractions on a real
    corpus ran 391-994 words/page and silent failures 0-10.8, with nothing in
    between — the threshold sits in an empty band."""
    real = {"pages": 44, "outputs": [{"words": 23193}], "method": "text-layer"}
    scan = {"pages": 44, "outputs": [{"words": 7}], "method": "text-layer"}
    assert sources.derivative_fidelity(real) == "text-only"
    assert sources.derivative_fidelity(scan) == "thin"
    assert sources.THIN_WORDS_PER_PAGE == 25.0


def test_fidelity_calls_no_text_empty_however_the_row_says_it():
    """Two spellings of the same nothing: a `not-extracted` row (what flip
    writes) and a row whose outputs total zero words (what a hand-written or
    third-party row might look like)."""
    assert sources.derivative_fidelity({"status": "not-extracted"}) == "empty"
    assert sources.derivative_fidelity({"outputs": [{"words": 0}]}) == "empty"


def test_fidelity_is_unknown_when_the_method_is_out_of_vocabulary():
    """A `method` that reads like a tool name means the record cannot say what
    kind of text this even is. The words-per-page evidence is still a fact, so
    a row with NO method is judged on its words — unlike capture_fidelity,
    whose size test needs the method to mean anything."""
    row = {"pages": 4, "outputs": [{"words": 4000}], "method": "pdftotext-v22"}
    assert sources.derivative_fidelity(row) == "unknown"
    assert sources.derivative_fidelity({"pages": 4, "outputs": [{"words": 4000}]}) == "text-only"
    assert sources.derivative_fidelity({"pages": 4, "outputs": [{"words": 8}]}) == "thin"


# --- primary_raw: one rule, previously written out three times ---------------


def test_primary_raw_finds_the_document_in_either_custody_shape(root):
    """`builtin:copy` writes `sources/raw/F1.pdf`; a fetcher writes a directory.
    The rule inside the directory is the one add_source uses to pick the page's
    `local`: the largest real file, never the flip.json envelope (which is
    metadata about a capture, and is always tiny)."""
    loose = capture(root, "F1")
    assert sources.primary_raw(root, "F1") == loose

    d = root / "sources" / "raw" / "A2"
    d.mkdir(parents=True)
    (d / "flip.json").write_bytes(b'{"flip": {"title": "x"}}' * 100)
    (d / "page.html").write_bytes(b"<html>short</html>")
    (d / "paper.pdf").write_bytes(b"x" * 5000)
    assert sources.primary_raw(root, "A2").name == "paper.pdf"


def test_media_family_collapses_only_what_shares_a_tool():
    """`.htm` and `.html` are the same format and one lane reads both. `.doc`,
    `.odt` and `.rtf` are NOT folded into `docx`: a tool that reads one often
    cannot read the others, and silently routing `.doc` at a docx-only lane
    would produce exactly the quiet failure this lane exists to catch. An
    unknown suffix becomes its own family, so an operator can configure
    `[extractors].epub` with no change here."""
    assert sources.media_family("a.pdf") == "pdf"
    assert sources.media_family("a.htm") == sources.media_family("a.html") == "html"
    assert sources.media_family("a.m4a") == sources.media_family("a.wav") == "audio"
    assert sources.media_family("a.docx") == "docx"
    assert sources.media_family("a.doc") == "doc"
    assert sources.media_family("a.odt") == "odt"
    assert sources.media_family("a.epub") == "epub"


def test_primary_raw_on_a_source_with_no_custody_says_capture_it_first(root):
    with pytest.raises(SystemExit) as ei:
        sources.primary_raw(root, "F9")
    assert "no raw custody for F9" in str(ei.value)
    assert "flip add-source" in str(ei.value)
    # a record capture holds no document, and the message says so rather than
    # sending someone to look for bytes that were never obtained
    assert "record capture holds no document" in str(ei.value)


def test_extracting_a_record_capture_is_refused_for_what_it_would_produce(
    root, tmp_path, monkeypatch
):
    """A record capture holds flip's note about a document it could not get
    (§5.1). An extractor pointed at that note would happily produce a text
    derivative *of the note* — a readable, hashed, logged file that is not the
    source and reads like one. Refuse, and say which rung to climb instead."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\njson = "{tool} {{src}} {{out}}"\n')
    d = root / "sources" / "raw" / "P1"
    d.mkdir(parents=True)
    (d / "record.json").write_text(
        json.dumps({"flip_record": 1, "target": "doi:10.1/x",
                    "document_in_custody": False}), encoding="utf-8",
    )
    with pytest.raises(SystemExit) as ei:
        sources.extract_text(root, "P1", method="structured")
    assert "P1 is a record capture" in str(ei.value)
    assert "no text in it to extract" in str(ei.value)
    assert not (root / "sources" / "text").exists()


# --- extract_text: the ledger row, and what it is for -----------------------


def test_one_extraction_writes_the_file_and_exactly_one_derivation_row(
    root, tmp_path, monkeypatch
):
    """The row is the point of the feature. Everything a later reader needs to
    decide what the words are worth: what they came FROM (path + hash + size),
    what made them (tool, version, the verbatim command template, the lane),
    HOW (method), and what came out (path + hash + size + words)."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch,
               f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = capture(root, "F1")
    row = sources.extract_text(root, "F1", method="text-layer", note="clean text layer")

    out = root / "sources" / "text" / "F1.txt"
    assert out.is_file()
    rows = read_jsonl(root / sources.DERIVATIONS)
    assert len(rows) == 1 and rows[0] == row
    assert row["source_id"] == "F1" and row["kind"] == "text"
    assert row["inputs"] == [
        {"path": "sources/raw/F1.pdf", "sha256": sha256_file(src), "bytes": src.stat().st_size}
    ]
    assert row["cmd"] == f"{tool} {{src}} {{out}}"     # verbatim, placeholders and all
    assert row["tool"] == tool.name
    assert row["method"] == "text-layer"
    assert row["note"] == "clean text layer" and row["actor"] == "agent:test"
    assert row["outputs"] == [
        {"path": "sources/text/F1.txt", "sha256": sha256_file(out),
         "bytes": out.stat().st_size, "words": 600}
    ]
    assert row["pages"] == 3 and row["words_per_page"] == 200.0
    # `fidelity` is DERIVED on read, never written into the row — the same
    # discipline as capture_fidelity and derive_grade. A value that cannot
    # drift from inputs sitting in its own append-only row is a value the
    # reader can always recompute, so storing it would buy nothing and add a
    # stored derivation.
    assert "fidelity" not in row
    assert sources.derivative_fidelity(row) == "text-only"
    assert "supersedes" not in row                     # nothing to supersede yet


def test_extraction_never_touches_raw_custody(root, tmp_path, monkeypatch):
    """A derivative may be overwritten. The bytes it was derived from may not —
    that rule is older than this lane and this lane does not get to bend it."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = capture(root, "F1")
    before = sha256_file(src)
    sources.extract_text(root, "F1", method="text-layer")
    sources.extract_text(root, "F1", method="ocr")
    assert sha256_file(src) == before


def test_re_extraction_records_what_it_replaced(root, tmp_path, monkeypatch):
    """Overwriting a derivative is safe *because* the log is append-only:
    `supersedes` names the sha256 of the output that is now gone from disk, so
    a claim quoting the old text can still be traced to the run that made it."""
    first = words_script(tmp_path, 600, name="first")
    second = make_script(tmp_path, "second",
                         'awk \'BEGIN{for(i=0;i<800;i++) printf "term%d ", i}\' > "$2"\n')
    set_config(
        tmp_path, monkeypatch,
        f'[extractors.pdf]\ndefault = "{first} {{src}} {{out}}"\n'
        f'ocr = "{second} {{src}} {{out}}"\n',
    )
    capture(root, "F1")
    old = sources.extract_text(root, "F1", method="text-layer")
    new = sources.extract_text(root, "F1", via="ocr")
    assert new["supersedes"] == old["outputs"][0]["sha256"]
    assert new["via"] == "ocr"
    assert sources.latest_derivation(root, "F1") == new


def test_a_lane_named_for_a_method_supplies_the_method(root, tmp_path, monkeypatch):
    """`[extractors.pdf].ocr` already says what it does. Making the operator
    repeat it in --method on every run is how a field ends up unfilled — and an
    unfilled method is the whole thing this feature exists to record."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch,
               f'[extractors.pdf]\nocr = "{tool} {{src}} {{out}}"\n'
               f'quick = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    assert sources.extract_text(root, "F1", via="ocr")["method"] == "ocr"
    # a lane named something else supplies nothing — flip does not guess, and
    # `text-layer` would be a lie in exactly the case that matters
    assert "method" not in sources.extract_text(root, "F1", via="quick", force=True)


def test_an_out_of_vocabulary_method_is_refused_with_the_reason(root, tmp_path, monkeypatch):
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    with pytest.raises(SystemExit) as ei:
        sources.extract_text(root, "F1", method="pdftotext")
    msg = str(ei.value)
    assert "invalid extraction method 'pdftotext'" in msg
    assert "text-layer" in msg and "ocr" in msg
    assert "not the same evidence" in msg


def test_a_failed_extraction_still_lands_in_the_ledger(root, tmp_path, monkeypatch):
    """"Tried and it broke" has to stay distinguishable from "never tried" —
    the same reason a failed capture writes its own provenance row."""
    tool = make_script(tmp_path, "brokenext", 'echo "no such font" >&2\nexit 4\n')
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    with pytest.raises(SystemExit):
        sources.extract_text(root, "F1", method="ocr")
    row = read_jsonl(root / sources.DERIVATIONS)[-1]
    assert row["status"] == "failed" and "exit 4" in row["error"]
    assert sources.latest_derivation(root, "F1") is None   # a finding, not a derivative


def test_the_empty_refusal_reads_the_operators_own_lanes_back(root, tmp_path, monkeypatch):
    """This is how "go hunt around for an OCR tool" stops being something an
    agent does from memory. flip may not know what fills a lane (§16) — it can
    read the config the operator wrote and print the runnable command."""
    silent = make_script(tmp_path, "silent", "exit 0\n")
    ocr = words_script(tmp_path, 600, name="ocrtool")
    set_config(
        tmp_path, monkeypatch,
        f'[extractors.pdf]\ndefault = "{silent} {{src}} {{out}}"\n'
        f'ocr = "{ocr} {{src}} {{out}}"\n[extractors]\nhtml = "{ocr} {{src}} {{out}}"\n',
    )
    capture(root, "F1")
    with pytest.raises(integrations.EmptyExtraction) as ei:
        sources.extract_text(root, "F1")
    msg = str(ei.value)
    assert "ran clean (exit 0) and produced no text" in msg
    assert "(3 pages)" in msg
    assert "--via ocr" in msg                      # the lane that could work
    assert "other media families configured here: html" in msg
    assert "custody is intact" in msg              # F1 is not damaged by this
    assert "OCR is the only answer" in msg


def test_the_empty_refusal_with_no_other_lane_says_to_configure_one(
    root, tmp_path, monkeypatch
):
    silent = make_script(tmp_path, "silent", "exit 0\n")
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{silent} {{src}} {{out}}"\n')
    capture(root, "F1")
    with pytest.raises(integrations.EmptyExtraction) as ei:
        sources.extract_text(root, "F1")
    msg = str(ei.value)
    assert "no other [extractors].pdf lane is configured on this machine" in msg
    assert str(integrations.config_path()) in msg


# --- the hand-edit guard ----------------------------------------------------


def test_a_hand_edited_derivative_is_refused_without_force(root, tmp_path, monkeypatch):
    """The append-only log is what lets flip tell its own last output from
    someone's work. A .txt whose sha256 matches no row was written by a person —
    a hand correction, a stitched transcript, a paste — and silently replacing
    it would destroy it with only the replacement visible in the log."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    sources.extract_text(root, "F1", method="text-layer")

    out = root / "sources" / "text" / "F1.txt"
    out.write_text("a person fixed the column order by hand\n", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        sources.extract_text(root, "F1", method="text-layer")
    msg = str(ei.value)
    assert "matches no row" in msg and "a person did" in msg
    assert "--force" in msg
    assert out.read_text().startswith("a person fixed")   # still there


def test_force_replaces_it_and_the_log_says_a_run_happened(root, tmp_path, monkeypatch):
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    sources.extract_text(root, "F1", method="text-layer")
    (root / "sources" / "text" / "F1.txt").write_text("hand edit\n", encoding="utf-8")

    row = sources.extract_text(root, "F1", method="text-layer", force=True,
                              note="hand edit was a stray paste")
    assert row["note"] == "hand edit was a stray paste"
    assert (root / "sources" / "text" / "F1.txt").read_text().startswith("word0 ")
    assert len(read_jsonl(root / sources.DERIVATIONS)) == 2


def test_a_derivative_flip_itself_wrote_is_replaced_without_ceremony(
    root, tmp_path, monkeypatch
):
    """The guard is about UNTRACKED work, not about overwriting as such. A file
    that hashes to a row in the log is flip's own last output and re-extracting
    it needs no flag."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    sources.extract_text(root, "F1", method="text-layer")
    sources.extract_text(root, "F1", method="text-layer")   # no --force needed
    assert len(read_jsonl(root / sources.DERIVATIONS)) == 2


# --- doctor -----------------------------------------------------------------


def add_page(root: Path, source_id: str, local: str, slug: str | None = None) -> None:
    ref = root / "references"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / f"{slug or source_id.lower()}.md").write_text(
        "---\n"
        "type: Source\n"
        f"id: {source_id}\n"
        f"aliases: [{source_id}]\n"
        f"title: \"{source_id}\"\n"
        f"local: {local}\n"
        "grade: \"?\"\n"
        "status: captured\n"
        "---\n"
        f"# {source_id}\n",
        encoding="utf-8",
    )


def codes(findings, code: str) -> list:
    return [f for f in findings if f.code == code]


def test_doctor_names_a_thin_derivative(root, tmp_path, monkeypatch):
    """The dangerous case, and the reason it is checked at all: unlike the empty
    extraction — which refuses and writes nothing — a thin one leaves a
    plausible-looking .txt on disk with a hash and a derivation row behind it."""
    tool = words_script(tmp_path, 9, name="thinext")
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    row = sources.extract_text(root, "F1", method="ocr")
    assert "fidelity" not in row  # derived on read, never stored
    assert sources.derivative_fidelity(row) == "thin"

    found = codes(doctor.run_doctor(root), "thin-derivative")
    assert len(found) == 1
    assert "9 words from a 3-page document" in found[0].message
    assert found[0].path == "sources/text/F1.txt"
    assert "raw custody is untouched" in found[0].message


def test_doctor_names_a_derivative_that_will_not_say_how(root, tmp_path, monkeypatch):
    """A quotation drawn from a text derivative cannot say whether it came from
    the document's own text layer or from an engine reading a picture of it,
    unless the row says. Missing is an expected-until-use nudge; an out-of-
    vocabulary value that reads like a tool name is a plain warning."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    sources.extract_text(root, "F1")

    found = codes(doctor.run_doctor(root), "unvocabularied-extraction")
    assert len(found) == 1 and found[0].expected is True
    assert "records no extraction method" in found[0].message

    rows = read_jsonl(root / sources.DERIVATIONS)
    rows[-1]["method"] = "pdftotext"
    (root / sources.DERIVATIONS).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    found = codes(doctor.run_doctor(root), "unvocabularied-extraction")
    assert len(found) == 1 and found[0].expected is False
    assert "reads like a tool name" in found[0].message


def test_doctor_names_a_text_file_no_row_accounts_for(root, tmp_path, monkeypatch):
    """The other side of the hand-edit guard: an unlogged .txt is not an error —
    people write these — but nothing says what it was derived from, by what
    tool, or by what method, and `flip extract` will refuse to touch it."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "nothing"))
    add_page(root, "F1", "sources/raw/F1.pdf")
    capture(root, "F1")
    text = root / "sources" / "text"
    text.mkdir(parents=True)
    (text / "F1.txt").write_text("typed up by hand from the printout\n", encoding="utf-8")

    found = codes(doctor.run_doctor(root), "unlogged-derivative")
    assert len(found) == 1 and found[0].path == "sources/text/F1.txt"
    assert "flip did not write these bytes, so a person did" in found[0].message


def test_doctor_notices_a_captured_document_with_a_lane_and_no_derivative(
    root, tmp_path, monkeypatch
):
    """An expected-until-use notice, not a defect. It only fires when the
    operator has actually configured a lane for that media family — flip cannot
    know what fills a role (§16), but it can see whether something does."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")

    found = codes(doctor.run_doctor(root), "missing-derivative")
    assert len(found) == 1 and found[0].expected is True
    assert "flip extract F1" in found[0].message

    # once an extraction has been attempted — even one that found nothing —
    # the notice stops: the question has been asked and answered in the ledger
    sources.extract_text(root, "F1", method="text-layer")
    assert codes(doctor.run_doctor(root), "missing-derivative") == []


def test_missing_derivative_does_not_depend_on_what_this_machine_has_installed(
    root, tmp_path, monkeypatch
):
    """doctor reads the notebook, not the machine.

    Gating this notice on a configured lane was tried and reverted: it made two
    people linting the same committed notebook get different findings, and the
    one who saw nothing was the one with no extractor configured — exactly the
    person who most needed to know the text was missing. "This capture has no
    readable derivative" is true whatever is installed, and it presumes no tool
    (reading the bytes yourself is a legitimate answer), so it fires either way
    and only the advice changes.
    """
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "nothing"))
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    found = codes(doctor.run_doctor(root), "missing-derivative")
    assert len(found) == 1
    assert "no [extractors].pdf lane is configured here" in found[0].message
    assert "still a source" in found[0].message
    assert found[0].expected is True  # appears with use; not breakage


def test_a_broken_derivations_ledger_is_bad_jsonl_and_nothing_else(root, monkeypatch, tmp_path):
    """`derived/_derivations.jsonl` was already in LEDGERS, so parse checking is
    free — and the derivative checks must not pile a second, confusing finding
    on top of the one that explains everything."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "nothing"))
    log = root / sources.DERIVATIONS
    log.parent.mkdir(parents=True)
    log.write_text("{not json at all\n", encoding="utf-8")
    findings = doctor.run_doctor(root)
    assert len(codes(findings, "bad-jsonl")) == 1
    assert codes(findings, "thin-derivative") == []


def test_every_new_code_is_registered():
    """Discipline files reference check codes by name; an unregistered one is
    itself an ERROR (`bad-discipline`)."""
    for code in ("thin-derivative", "missing-derivative", "unlogged-derivative",
                 "unvocabularied-extraction"):
        assert code in doctor.CHECK_CODES


# --- CLI --------------------------------------------------------------------


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


@pytest.fixture
def nb(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_ACTOR", "human:test")
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    dest = tmp_path / "demo"
    assert invoke(["new", "demo", "--kind", "scout", "--dest", str(dest)]).exit_code == 0
    monkeypatch.chdir(dest)
    return dest.resolve()


def test_cli_extract_reports_the_shape_of_what_it_made(nb, tmp_path, monkeypatch):
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = tmp_path / "report.pdf"
    src.write_bytes(PDF_3PAGE)
    assert invoke(["add-source", str(src)]).exit_code == 0

    result = invoke(["extract", "F1", "--method", "text-layer"])
    assert result.exit_code == 0, result.output
    assert "sources/text/F1.txt · 600 words" in result.output
    assert "3 pages · 200.0 words/page · text-only" in result.output
    assert "(text-layer)" in result.output


def test_cli_warns_loudly_the_moment_a_thin_derivative_lands(nb, tmp_path, monkeypatch):
    """At extraction time, not only at doctor time — the same reason the thin
    CAPTURE warning moved. Doctor runs later, and by then the thin text has
    been read, quoted, and cited."""
    tool = words_script(tmp_path, 9, name="thinext")
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = tmp_path / "scan.pdf"
    src.write_bytes(PDF_3PAGE)
    invoke(["add-source", str(src)])

    result = invoke(["extract", "F1", "--method", "ocr"])
    assert result.exit_code == 0, result.output
    assert "warning: thin derivative" in result.output
    assert "9 words from a 3-page document" in result.output
    assert "read sources/text/F1.txt before you quote it" in result.output


def test_cli_nudges_once_when_a_document_lands_and_a_lane_exists(nb, tmp_path, monkeypatch):
    """One line, at capture. Extraction stays on demand — `add-source`'s
    contract is custody, an OCR pass can run for minutes, and a cheap verb that
    sometimes becomes expensive is worse than a verb you have to type. But
    saying nothing at all is how `sources/text/` stayed empty for years."""
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = tmp_path / "report.pdf"
    src.write_bytes(PDF_3PAGE)
    result = invoke(["add-source", str(src)])
    assert "flip extract F1" in result.output
    assert not (nb / "sources" / "text").exists()   # nudged, not done

    # no lane for this family: no nudge, because there is nothing to act on
    csv = tmp_path / "table.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    assert "flip extract F2" not in invoke(["add-source", str(csv)]).output


def test_cli_add_source_extract_does_both(nb, tmp_path, monkeypatch):
    tool = words_script(tmp_path, 600)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    src = tmp_path / "report.pdf"
    src.write_bytes(PDF_3PAGE)
    result = invoke(["add-source", str(src), "--extract"])
    assert result.exit_code == 0, result.output
    assert (nb / "sources" / "text" / "F1.txt").is_file()
    assert "600 words" in result.output
    # and it still tells you to judge the source: capture is custody, and a
    # derivative is not a judgment either
    assert "judge it after reading" in result.output


def test_cli_record_and_extract_together_are_refused(nb, tmp_path, monkeypatch):
    """A record capture holds no bytes of the document by definition, so there
    is nothing for an extractor to read — and the two flags together describe
    two incompatible intentions rather than one."""
    result = invoke(["add-source", "https://gone.example/x", "--record",
                     "--note", "tried three rungs", "--extract"])
    assert result.exit_code == 1
    assert "has nothing to read" in result.output


# --- regressions found by dogfooding (2026-08-09) ----------------------------


def test_a_failed_extraction_does_not_silence_the_missing_derivative_notice(
    root, tmp_path, monkeypatch
):
    """A broken lane settled nothing, so the text is still missing.

    Counting any row as an attempt let a misconfigured lane quiet the notice
    permanently: on a real notebook an html lane failed twice — wrong tool, then
    wrong flag — and doctor then reported nothing missing while nothing had been
    extracted. Only outputs, or a clean `not-extracted` run, settle it.
    """
    broken = make_script(tmp_path, "brokenext", "exit 3\n")
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{broken} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    with pytest.raises(SystemExit):
        sources.extract_text(root, "F1")
    assert len(codes(doctor.run_doctor(root), "missing-derivative")) == 1


def test_a_clean_run_that_found_no_text_does_settle_it(root, tmp_path, monkeypatch):
    """The counterpart: `not-extracted` is a finding ABOUT the document — there
    is no text layer in it — and re-asking every run would be nagging for a fact
    already established."""
    empty = make_script(tmp_path, "emptyext", ': > "$2"\n')
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{empty} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    with pytest.raises(SystemExit):
        sources.extract_text(root, "F1")
    assert codes(doctor.run_doctor(root), "missing-derivative") == []


def test_a_directory_at_the_output_path_is_a_flip_refusal_not_a_stack_trace(
    root, tmp_path, monkeypatch
):
    """An extractor whose {out} lands on a flag meaning output DIRECTORY makes
    one. That happened on a real notebook, and the NEXT run died inside the tool
    on IsADirectoryError — blaming the retry for what the first run left. Neither
    --force nor the hand-edit guard covers it: the question is not whose bytes
    those are, there are no bytes."""
    tool = words_script(tmp_path, 50)
    set_config(tmp_path, monkeypatch, f'[extractors]\npdf = "{tool} {{src}} {{out}}"\n')
    capture(root, "F1")
    add_page(root, "F1", "sources/raw/F1.pdf")
    (root / "sources" / "text" / "F1.txt").mkdir(parents=True)

    with pytest.raises(SystemExit) as e:
        sources.extract_text(root, "F1")
    msg = str(e.value)
    assert "is a directory" in msg
    assert "flip config show" in msg          # the lane is where the fault is
    assert "omit {out}" in msg                # and the shape that fits such a tool
    # --force is about replacing bytes, and cannot help here
    with pytest.raises(SystemExit, match="is a directory"):
        sources.extract_text(root, "F1", force=True)
