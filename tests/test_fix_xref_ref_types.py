import xml.etree.ElementTree as ET

from latex_jats.convert import fix_xref_ref_types


def _make_doc(body, back=""):
    return f"<article><body>{body}</body><back>{back}</back></article>"


def test_fig_ref_type(xml_file):
    xml = _make_doc(
        '<fig id="fig1"/><p><xref rid="fig1">1</xref></p>'
    )
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "fig"


def test_table_ref_type(xml_file):
    xml = _make_doc(
        '<table-wrap id="tab1"/><p><xref rid="tab1">1</xref></p>'
    )
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "table"


def test_sec_ref_type(xml_file):
    xml = _make_doc(
        '<sec id="sec1"><title>Intro</title></sec><p><xref rid="sec1">1</xref></p>'
    )
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "sec"


def test_app_ref_type(xml_file):
    xml = _make_doc(
        '<p><xref rid="app1">A</xref></p>',
        '<app id="app1"><title>Appendix</title></app>',
    )
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "sec"


def test_existing_ref_type_not_overwritten(xml_file):
    xml = _make_doc(
        '<fig id="fig1"/><p><xref rid="fig1" ref-type="bibr">1</xref></p>'
    )
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "bibr"


def test_unknown_rid_left_without_ref_type(xml_file):
    xml = _make_doc('<p><xref rid="unknown">X</xref></p>')
    path = xml_file(xml)
    fix_xref_ref_types(path)
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") is None
