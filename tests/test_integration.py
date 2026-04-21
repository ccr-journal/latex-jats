"""Integration tests: full LaTeX → JATS pipeline (requires latexmlc)."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

import shutil

from latex_jats.convert import (
    collapse_affiliations,
    preprocess_for_latexml,
    run_latexmlc,
    validate_jats,
)

FIXTURES = Path(__file__).parent / "fixtures" / "latex"


def _prepare_fixture(fixture_tex: Path, tmp_path: Path) -> Path:
    """Copy a fixture to tmp_path and apply LaTeXML preprocessing. Returns the copied main .tex path."""
    workspace = tmp_path / "workspace"
    shutil.copytree(fixture_tex.parent, workspace)
    preprocess_for_latexml(workspace)
    return workspace / fixture_tex.name


@pytest.mark.integration
def test_citations_linked(tmp_path):
    """Citations link to bibliography entries and display author-year text."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "citations.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    ref_ids = {ref.get("id") for ref in root.findall(".//ref-list//ref") if ref.get("id")}
    assert ref_ids, "No refs in ref-list"
    xrefs = [x for x in root.findall(".//xref") if x.get("rid") in ref_ids]
    assert xrefs, "No xrefs pointing to bibliography entries"
    for xref in xrefs:
        assert xref.text and xref.text.strip(), f"No display text on xref: {ET.tostring(xref, encoding='unicode')}"

    def norm(text):
        """Normalize LaTeXML's protected spaces (nbsp + U+0335) to plain spaces."""
        return text.replace("\xa0", " ").replace("\u0335", "") if text else ""

    # Single-author: should contain "Smith" and "2020"
    single = xrefs[0]
    assert "Smith" in norm(single.text), f"Expected 'Smith' in citation text, got: {single.text!r}"
    assert "2020" in norm(single.text), f"Expected '2020' in citation text, got: {single.text!r}"

    # Two-author: should contain both surnames joined with "&" (APA style)
    two_author = xrefs[1]
    txt2 = norm(two_author.text)
    assert "Jones" in txt2 and "&" in txt2 and "Brown" in txt2, \
        f"Expected 'Jones & Brown' in two-author text, got: {two_author.text!r}"
    assert "2021" in txt2, f"Expected '2021' in citation text, got: {two_author.text!r}"

    # Three-plus-author: should contain "et al." (APA style)
    three_plus = xrefs[2]
    txt3 = norm(three_plus.text)
    assert "Garcia" in txt3 and "et al." in txt3, \
        f"Expected 'Garcia et al.' in 3+ author text, got: {three_plus.text!r}"
    assert "2022" in txt3, f"Expected '2022' in citation text, got: {three_plus.text!r}"

    # Grouped citations should be separated by semicolons, not commas
    body_text = " ".join(root.find(".//body").itertext())
    body_text = norm(body_text)
    assert "; " in body_text, f"Expected semicolons in grouped citations, got: {body_text[:500]!r}"


@pytest.mark.integration
def test_citation_optional_args(tmp_path):
    """Citation commands with optional prenote/postnote arguments render correctly."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "citations.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()

    def norm(text):
        return text.replace("\xa0", " ").replace("\u0335", "") if text else ""

    body = root.find(".//body")
    body_text = norm(" ".join(body.itertext()))

    # \parencite[p.~42]{smith2020test} — postnote only
    assert "(Smith," in body_text and "p. 42)" in body_text, \
        f"Expected parencite postnote in body text"

    # \parencite[cf.][p.~42]{smith2020test} — prenote and postnote
    assert "(cf. Smith," in body_text, \
        f"Expected parencite prenote 'cf.' in body text"

    # \textcite[p.~42]{jones2021multi} — textual with postnote
    # Should be: Jones & Brown (2021, p. 42)
    assert "Brown (" in body_text or "Brown(" in body_text, \
        f"Expected textcite author before parens in body text"
    assert "p. 42)" in body_text, \
        f"Expected textcite postnote in body text"

    # \textcite[see][p.~99]{team2022three} — textual with prenote+postnote
    assert "(see" in body_text, \
        f"Expected textcite prenote 'see' in body text"
    assert "p. 99)" in body_text, \
        f"Expected textcite postnote 'p. 99' in body text"

    # \citeyear[p.~42]{smith2020test} — year with postnote
    assert "2020" in body_text and "p. 42" in body_text

    # No rid="[" anywhere — the bug that prompted these fixes
    xrefs = root.findall(".//xref")
    for xref in xrefs:
        assert xref.get("rid") != "[", \
            f"Found xref with rid='[': {ET.tostring(xref, encoding='unicode')}"


@pytest.mark.integration
def test_abstract_and_keywords(tmp_path):
    """\\abstract{} and \\keywords{} produce <abstract> and <kwd-group> in JATS."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "authors.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()

    abstract = root.find(".//abstract")
    assert abstract is not None, "No <abstract> element in output"
    abstract_text = " ".join(abstract.itertext())
    assert "test abstract" in abstract_text.lower()

    kwd_group = root.find(".//kwd-group")
    assert kwd_group is not None, "No <kwd-group> element in output"
    kwds = [kwd.text for kwd in kwd_group.findall("kwd")]
    assert kwds, "No <kwd> elements in <kwd-group>"
    assert all(kwd == kwd.strip() for kwd in kwds), f"Keywords have surrounding whitespace: {kwds}"


@pytest.mark.integration
def test_acknowledgements(tmp_path):
    """\\acknowledgements{} produces <back><ack> with the content."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "authors.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    ack = root.find(".//back/ack")
    assert ack is not None, "Expected <ack> under <back>"
    text = " ".join(ack.itertext())
    assert "reviewers" in text, f"Expected 'reviewers' in ack text, got: {text!r}"


@pytest.mark.integration
def test_authors_names_and_affiliations(tmp_path):
    """Authors are split into surname/given-names with spaces preserved."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "authors.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    contribs = root.findall(".//contrib[@contrib-type='author']")
    assert len(contribs) == 3, f"Expected 3 authors, got {len(contribs)}"

    names = [(c.findtext(".//surname"), c.findtext(".//given-names")) for c in contribs]

    # First author: Jane Doe
    assert names[0][0] == "Doe"
    assert names[0][1] == "Jane"

    # Second author: John van der Berg — given-names must have spaces (the bug we fixed)
    assert names[1][0] == "Berg"
    assert names[1][1] == "John van der"

    # Third author: Alice Smith — shares affiliation with Jane Doe
    assert names[2][0] == "Smith"
    assert names[2][1] == "Alice"


@pytest.mark.integration
def test_collapse_affiliations_post_pipeline(tmp_path):
    """After collapse_affiliations runs, shared affiliations collapse to a
    single <aff> sibling of <contrib> inside <contrib-group>, linked by
    <xref ref-type="aff" rid="affN"/>.
    """
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "authors.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)
    collapse_affiliations(str(output))

    cg = ET.parse(output).getroot().find(".//contrib-group")
    assert cg is not None

    # 3 contribs, each with exactly one <xref ref-type="aff">; no nested <aff>.
    contribs = cg.findall("contrib")
    assert len(contribs) == 3
    rids = []
    for c in contribs:
        assert c.find("aff") is None
        xrefs = c.findall("xref")
        assert len(xrefs) == 1 and xrefs[0].get("ref-type") == "aff"
        rids.append(xrefs[0].get("rid"))

    # 2 unique <aff> siblings of <contrib> in first-occurrence order.
    affs = cg.findall("aff")
    assert [a.get("id") for a in affs] == ["aff1", "aff2"]
    assert affs[0].text == "University of Amsterdam"
    assert affs[1].text == "Radboud University"

    # Authors 1 and 3 share aff1 (University of Amsterdam); author 2 is aff2.
    assert rids == ["aff1", "aff2", "aff1"]


@pytest.mark.integration
def test_subfigures_produce_fig_group(tmp_path):
    """\\subfloat inside a figure environment produces <fig-group> with child <fig> elements."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "subfigure.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    fig_groups = root.findall(".//fig-group")
    assert fig_groups, "No <fig-group> element found — subfigures should produce <fig-group>"

    # The fig-group should contain the individual subfig <fig> elements directly
    for fg in fig_groups:
        child_figs = fg.findall("fig")
        assert child_figs, f"<fig-group> has no child <fig> elements: {ET.tostring(fg, encoding='unicode')}"
        # No nested fig-inside-fig
        for fig in child_figs:
            assert not fig.findall("fig"), "Nested <fig> inside <fig> found; expected flat structure under <fig-group>"


@pytest.mark.integration
def test_adjustbox_table_structure(tmp_path):
    """adjustbox inside a table environment should be transparent — <table> is a direct child of <table-wrap>."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "adjustbox_table.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    table_wraps = root.findall(".//table-wrap")
    assert table_wraps, "No <table-wrap> found"
    for tw in table_wraps:
        tables = tw.findall("table")
        assert tables, f"<table-wrap> {tw.get('id')} has no direct <table> child"
        # table must NOT be nested inside <p>
        for p in tw.findall("p"):
            assert p.find(".//table") is None, "<table> found nested inside <p> within <table-wrap>"


@pytest.mark.integration
def test_description_list_produces_def_list(tmp_path):
    """\\begin{description}\\item[LABEL] produces JATS <def-list> with <term> labels."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "description.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)

    root = ET.parse(output).getroot()
    def_lists = root.findall(".//def-list")
    assert def_lists, "No <def-list> found — description should map to def-list"

    def_items = def_lists[0].findall("def-item")
    assert len(def_items) == 3, f"Expected 3 def-items, got {len(def_items)}"

    # Item 1: \item[RQ1:] — plain-text label
    term1 = def_items[0].find("term")
    assert term1 is not None, "First def-item has no <term>"
    assert "".join(term1.itertext()) == "RQ1:", f"Expected 'RQ1:' in term, got {term1.text!r}"
    def1 = def_items[0].find("def")
    assert def1 is not None and def1.find("p") is not None, "First def-item has no <def><p>"
    assert "How effectively" in "".join(def1.itertext())

    # Item 2: \item[\textbf{Donor Rate:}] — label with nested bold should survive as <bold>
    term2 = def_items[1].find("term")
    bold2 = term2.find("bold")
    assert bold2 is not None, \
        f"Expected <bold> inside <term>, got: {ET.tostring(term2, encoding='unicode')}"
    assert bold2.text == "Donor Rate:", f"Expected 'Donor Rate:' inside <bold>, got {bold2.text!r}"
    # No double-wrapping: <term> should have no direct text content besides the <bold>
    assert term2.find("bold/bold") is None, "Label should not be double-wrapped in <bold>"

    # Item 3: bare \item — empty <term>, still has <def>
    term3 = def_items[2].find("term")
    assert term3 is not None, "Bare item missing <term>"
    assert not (term3.text and term3.text.strip()) and len(term3) == 0, \
        f"Bare item <term> should be empty, got: {ET.tostring(term3, encoding='unicode')}"
    def3 = def_items[2].find("def")
    assert def3 is not None and def3.find("p") is not None
    assert "bare item" in "".join(def3.itertext())


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("jing"), reason="jing not installed")
def test_jats_validates(tmp_path):
    """Output JATS XML from the authors fixture validates against the JATS Publishing 1.2 RNG schema."""
    output = tmp_path / "output.xml"
    tex = _prepare_fixture(FIXTURES / "authors.tex", tmp_path)
    run_latexmlc(str(tex), str(output), log_dir=tmp_path)
    errors = validate_jats(str(output))
    assert not errors, f"JATS validation errors:\n" + "\n".join(errors)
