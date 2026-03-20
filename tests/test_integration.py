"""Integration tests: full LaTeX → JATS pipeline (requires latexmlc)."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from latex_jats.convert import run_latexmlc

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

    # Multi-author: should contain "et al." and "2021"
    multi = xrefs[1]
    assert "et al." in norm(multi.text), f"Expected 'et al.' in multi-author text, got: {multi.text!r}"
    assert "2021" in norm(multi.text), f"Expected '2021' in citation text, got: {multi.text!r}"


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
