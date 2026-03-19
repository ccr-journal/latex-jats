"""Integration tests: full LaTeX → JATS pipeline (requires latexmlc)."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from latex_jats.convert import run_latexmlc

FIXTURES = Path(__file__).parent / "fixtures" / "latex"


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
