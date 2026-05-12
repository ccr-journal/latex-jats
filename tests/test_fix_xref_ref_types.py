import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import fix_xref_ref_types


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


def test_xref_to_fig_group_warns(xml_file, caplog):
    xml = _make_doc(
        '<fig-group id="FG1">'
        '<fig id="FG1.sf1"/><fig id="FG1.sf2"/>'
        '</fig-group>'
        '<p><xref rid="FG1">1</xref></p>'
    )
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_xref_ref_types(path)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "FG1" in warnings[0].message
    # The xref itself is left alone — no ref-type rewriting, no rid rewrite.
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("rid") == "FG1"
    assert xref.get("ref-type") is None


def test_xref_to_inner_fig_does_not_warn(xml_file, caplog):
    xml = _make_doc(
        '<fig-group id="FG1">'
        '<fig id="FG1.sf1"/><fig id="FG1.sf2"/>'
        '</fig-group>'
        '<p><xref rid="FG1.sf1">1a</xref></p>'
    )
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_xref_ref_types(path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
    xref = ET.parse(path).getroot().find(".//xref")
    assert xref.get("ref-type") == "fig"
