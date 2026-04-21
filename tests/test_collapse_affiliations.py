"""Unit tests for collapse_affiliations: dedupe affs and move to contrib-group siblings."""

import xml.etree.ElementTree as ET

from latex_jats.convert import collapse_affiliations


def _write_xml(tmp_path, content):
    p = tmp_path / "article.xml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _wrap(contrib_group_inner: str) -> str:
    return f"""\
<article>
  <front>
    <article-meta>
      <contrib-group>
{contrib_group_inner}
      </contrib-group>
    </article-meta>
  </front>
</article>"""


def test_three_authors_all_share_one_aff(tmp_path):
    """All authors share one affiliation → one <aff id='aff1'>, three xrefs."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>Kathirgamalingam</surname><given-names>Ahrabhi</given-names></name>
          <aff>Computational Communication Science Lab, University of Vienna</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Lind</surname><given-names>Fabienne</given-names></name>
          <aff>Computational Communication Science Lab, University of Vienna</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Boomgaarden</surname><given-names>Hajo G.</given-names></name>
          <aff>Computational Communication Science Lab, University of Vienna</aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    contribs = cg.findall("contrib")
    affs = cg.findall("aff")

    assert len(contribs) == 3
    assert len(affs) == 1
    assert affs[0].get("id") == "aff1"
    assert affs[0].text.strip() == "Computational Communication Science Lab, University of Vienna"

    for contrib in contribs:
        assert contrib.find("aff") is None
        xrefs = contrib.findall("xref")
        assert len(xrefs) == 1
        assert xrefs[0].get("ref-type") == "aff"
        assert xrefs[0].get("rid") == "aff1"


def test_four_authors_mixed_unique_and_shared(tmp_path):
    """Authors 2 & 4 share; 1 & 3 unique → 3 <aff> siblings in first-seen order."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>El Damanhoury</surname><given-names>Kareem</given-names></name>
          <aff>University of Denver</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Winkler</surname><given-names>Carol</given-names></name>
          <aff>Georgia State University</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Lokmanoglu</surname><given-names>Ayse D.</given-names></name>
          <aff>Boston University</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Chen Glanz</surname><given-names>Keyu Alexander</given-names></name>
          <aff>Georgia State University</aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    affs = cg.findall("aff")
    assert [a.get("id") for a in affs] == ["aff1", "aff2", "aff3"]
    assert affs[0].text == "University of Denver"
    assert affs[1].text == "Georgia State University"
    assert affs[2].text == "Boston University"

    rids = [c.find("xref").get("rid") for c in cg.findall("contrib")]
    assert rids == ["aff1", "aff2", "aff3", "aff2"]


def test_all_unique_affiliations(tmp_path):
    """All unique → N aff siblings, N distinct rids."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>Doe</surname><given-names>Jane</given-names></name>
          <aff>University A</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Berg</surname><given-names>John</given-names></name>
          <aff>University B</aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    affs = cg.findall("aff")
    assert [a.get("id") for a in affs] == ["aff1", "aff2"]
    rids = [c.find("xref").get("rid") for c in cg.findall("contrib")]
    assert rids == ["aff1", "aff2"]


def test_contrib_without_aff(tmp_path):
    """Contrib with no <aff> passes through (no xref added, no orphan aff)."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>Doe</surname><given-names>Jane</given-names></name>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    assert cg.findall("aff") == []
    contrib = cg.find("contrib")
    assert contrib.find("xref") is None


def test_no_contrib_group_is_noop(tmp_path):
    """Article without contrib-group parses and returns cleanly."""
    xml_file = _write_xml(tmp_path, """\
<article>
  <front>
    <article-meta>
      <article-id>test</article-id>
    </article-meta>
  </front>
</article>""")

    collapse_affiliations(xml_file)

    root = ET.parse(xml_file).getroot()
    assert root.find(".//contrib-group") is None


def test_whitespace_only_differences_collapse(tmp_path):
    """Two affs that differ only in whitespace collapse to one unique aff."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>A</surname><given-names>A</given-names></name>
          <aff>University of Vienna</aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>B</surname><given-names>B</given-names></name>
          <aff>University   of  Vienna</aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    assert len(cg.findall("aff")) == 1
    rids = [c.find("xref").get("rid") for c in cg.findall("contrib")]
    assert rids == ["aff1", "aff1"]


def test_aff_inner_markup_preserved(tmp_path):
    """Inner markup of the first <aff> occurrence is kept (e.g. institution-wrap)."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>A</surname><given-names>A</given-names></name>
          <aff><institution-wrap><institution>University of Vienna</institution></institution-wrap></aff>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>B</surname><given-names>B</given-names></name>
          <aff><institution-wrap><institution>University of Vienna</institution></institution-wrap></aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    affs = cg.findall("aff")
    assert len(affs) == 1
    inst = affs[0].find("institution-wrap/institution")
    assert inst is not None
    assert inst.text == "University of Vienna"


def test_empty_aff_is_dropped(tmp_path):
    """An <aff/> with no text is silently removed (no xref, no sibling)."""
    xml_file = _write_xml(tmp_path, _wrap("""\
        <contrib contrib-type="author">
          <name><surname>A</surname><given-names>A</given-names></name>
          <aff></aff>
        </contrib>"""))

    collapse_affiliations(xml_file)

    cg = ET.parse(xml_file).getroot().find(".//contrib-group")
    assert cg.findall("aff") == []
    assert cg.find("contrib").find("xref") is None
