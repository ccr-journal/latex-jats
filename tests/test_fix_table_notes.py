import xml.etree.ElementTree as ET
from latex_jats.convert import fix_table_notes


MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      {table_wrap}
    </sec>
  </body>
</article>"""


def test_stray_p_moved_to_table_wrap_foot(xml_file):
    xml = MINIMAL_DOC.format(table_wrap="""\
<table-wrap id="T1">
  <table><tr><td>data</td></tr></table>
  <p>Note: values are approximate.</p>
</table-wrap>""")
    path = xml_file(xml)
    fix_table_notes(path)

    root = ET.parse(path).getroot()
    tw = root.find(".//table-wrap")
    # stray <p> should be gone from direct children
    assert tw.find("p") is None
    # <table-wrap-foot> should exist and contain the <p>
    foot = tw.find("table-wrap-foot")
    assert foot is not None
    p = foot.find("p")
    assert p is not None
    assert "values are approximate" in p.text


def test_no_stray_p_unchanged(xml_file):
    xml = MINIMAL_DOC.format(table_wrap="""\
<table-wrap id="T1">
  <table><tr><td>data</td></tr></table>
</table-wrap>""")
    path = xml_file(xml)
    fix_table_notes(path)

    root = ET.parse(path).getroot()
    tw = root.find(".//table-wrap")
    assert tw.find("table-wrap-foot") is None
