"""Integration tests: full LaTeX → JATS pipeline (requires latexmlc)."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

import shutil

from latex_jats.convert import run_latexmlc, validate_jats

FIXTURES = Path(__file__).parent / "fixtures" / "latex"


@pytest.mark.integration
def test_citations_linked(tmp_path):
    """Citations link to bibliography entries and display author-year text."""
    output = tmp_path / "output.xml"
    run_latexmlc(str(FIXTURES / "citations.tex"), str(output))

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
def test_abstract_and_keywords(tmp_path):
    """\\abstract{} and \\keywords{} produce <abstract> and <kwd-group> in JATS."""
    output = tmp_path / "output.xml"
    run_latexmlc(str(FIXTURES / "authors.tex"), str(output))

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
def test_authors_names_and_affiliations(tmp_path):
    """Authors are split into surname/given-names with spaces preserved."""
    output = tmp_path / "output.xml"
    run_latexmlc(str(FIXTURES / "authors.tex"), str(output))

    root = ET.parse(output).getroot()
    contribs = root.findall(".//contrib[@contrib-type='author']")
    assert len(contribs) == 2, f"Expected 2 authors, got {len(contribs)}"

    names = [(c.findtext(".//surname"), c.findtext(".//given-names")) for c in contribs]

    # First author: Jane Doe
    assert names[0][0] == "Doe"
    assert names[0][1] == "Jane"

    # Second author: John van der Berg — given-names must have spaces (the bug we fixed)
    assert names[1][0] == "Berg"
    assert names[1][1] == "John van der"


@pytest.mark.integration
def test_subfigures_produce_fig_group(tmp_path):
    """\\subfloat inside a figure environment produces <fig-group> with child <fig> elements."""
    output = tmp_path / "output.xml"
    run_latexmlc(str(FIXTURES / "subfigure.tex"), str(output))

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
@pytest.mark.skipif(not shutil.which("jing"), reason="jing not installed")
def test_jats_validates(tmp_path):
    """Output JATS XML from the authors fixture validates against the JATS Publishing 1.2 RNG schema."""
    output = tmp_path / "output.xml"
    run_latexmlc(str(FIXTURES / "authors.tex"), str(output))
    errors = validate_jats(str(output))
    assert not errors, f"JATS validation errors:\n" + "\n".join(errors)
