import xml.etree.ElementTree as ET

from latex_jats.convert import fix_appendix_labels

MINIMAL_DOC = """\
<article>
  <body>
    <sec><p>Body text with <xref rid="{xref_rid}">{xref_text}</xref>.</p></sec>
  </body>
  <back>
    <app-group>
      {apps}
    </app-group>
  </back>
</article>"""


def test_single_app_tables_relabeled(xml_file):
    apps = """\
<app id="A1">
  <title>Appendix A Appendix</title>
  <table-wrap id="A1.T5"><label>Table 5:</label></table-wrap>
  <table-wrap id="A1.T6"><label>Table 6:</label></table-wrap>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A1.T5", xref_text="5")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    labels = [tw.find("label").text for tw in root.findall(".//app//table-wrap")]
    assert labels == ["Table A1:", "Table A2:"]


def test_multiple_apps_correct_letters(xml_file):
    apps = """\
<app id="A1">
  <title>Appendix A Tables</title>
  <table-wrap id="A1.T5"><label>Table 5:</label></table-wrap>
</app>
<app id="A2">
  <title>Appendix B Figures</title>
  <fig id="A2.F8"><label>Figure 8:</label></fig>
  <fig id="A2.F9"><label>Figure 9:</label></fig>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A2.F8", xref_text="8")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    table_labels = [tw.find("label").text for tw in root.findall(".//app[@id='A1']//table-wrap")]
    fig_labels = [f.find("label").text for f in root.findall(".//app[@id='A2']//fig")]
    assert table_labels == ["Table A1:"]
    assert fig_labels == ["Figure B1:", "Figure B2:"]


def test_mixed_tables_and_figures_separate_counters(xml_file):
    apps = """\
<app id="A1">
  <title>Appendix A Mixed</title>
  <table-wrap id="A1.T5"><label>Table 5:</label></table-wrap>
  <fig id="A1.F8"><label>Figure 8:</label></fig>
  <table-wrap id="A1.T6"><label>Table 6:</label></table-wrap>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A1.T5", xref_text="5")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    table_labels = [tw.find("label").text for tw in root.findall(".//app//table-wrap")]
    fig_labels = [f.find("label").text for f in root.findall(".//app//fig")]
    assert table_labels == ["Table A1:", "Table A2:"]
    assert fig_labels == ["Figure A1:"]


def test_xref_text_updated(xml_file):
    apps = """\
<app id="A1">
  <title>Appendix A Appendix</title>
  <table-wrap id="A1.T5"><label>Table 5:</label></table-wrap>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A1.T5", xref_text="5")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    xref = root.find(".//xref[@rid='A1.T5']")
    assert xref is not None
    assert xref.text == "A1"


def test_no_app_group_is_noop(xml_file):
    xml = "<article><body><sec><p>No appendix here.</p></sec></body></article>"
    path = xml_file(xml)
    fix_appendix_labels(path)
    # Should not raise; document unchanged
    root = ET.parse(path).getroot()
    assert root.find(".//app-group") is None


def test_letter_from_title_not_position(xml_file):
    """When the title says 'Appendix C', use C even if it's the first app."""
    apps = """\
<app id="A3">
  <title>Appendix C Structural Topic Models</title>
  <fig id="A3.F10"><label>Figure 10:</label></fig>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A3.F10", xref_text="10")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    label = root.find(".//app//fig/label").text
    assert label == "Figure C1:"


def test_positional_fallback_when_no_title(xml_file):
    """When app has no title, use positional letter (first=A, second=B)."""
    apps = """\
<app id="A1">
  <table-wrap id="A1.T5"><label>Table 5:</label></table-wrap>
</app>
<app id="A2">
  <fig id="A2.F8"><label>Figure 8:</label></fig>
</app>"""
    xml = MINIMAL_DOC.format(apps=apps, xref_rid="A2.F8", xref_text="8")
    path = xml_file(xml)
    fix_appendix_labels(path)

    root = ET.parse(path).getroot()
    table_label = root.find(".//app[@id='A1']//table-wrap/label").text
    fig_label = root.find(".//app[@id='A2']//fig/label").text
    assert table_label == "Table A1:"
    assert fig_label == "Figure B1:"
