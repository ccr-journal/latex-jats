import xml.etree.ElementTree as ET

from latex_jats.convert import fix_nested_p

MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      {content}
    </sec>
  </body>
</article>"""


def test_nested_p_flattened(xml_file):
    """Inner <p> elements are promoted to siblings of the outer <p>."""
    xml = MINIMAL_DOC.format(
        content='<p>before<p>inner1</p>middle<p>inner2</p>after</p>'
    )
    path = xml_file(xml)
    fix_nested_p(path)

    root = ET.parse(path).getroot()
    sec = root.find(".//sec")
    ps = sec.findall("p")
    # Should have been split: wrapper(before), inner1, wrapper(middle), inner2
    # "after" may or may not produce a wrapper depending on content
    assert len(ps) >= 3
    # No nested <p> should remain
    for p in ps:
        assert p.find("p") is None


def test_nested_p_in_td(xml_file):
    """Nested <p> inside <td> (minipage pattern) is flattened."""
    xml = MINIMAL_DOC.format(
        content="""\
<table-wrap>
  <table>
    <tr>
      <td><p><bold>img1</bold><p>caption1</p><bold>img2</bold><p>caption2</p></p></td>
    </tr>
  </table>
</table-wrap>"""
    )
    path = xml_file(xml)
    fix_nested_p(path)

    root = ET.parse(path).getroot()
    td = root.find(".//td")
    # No nested <p> inside any <p>
    for p in td.findall(".//p"):
        assert p.find("p") is None


def test_no_nested_p_unchanged(xml_file):
    """A <p> without inner <p> is left alone."""
    xml = MINIMAL_DOC.format(content='<p>simple paragraph</p>')
    path = xml_file(xml)
    fix_nested_p(path)

    root = ET.parse(path).getroot()
    sec = root.find(".//sec")
    ps = sec.findall("p")
    assert len(ps) == 1
    assert ps[0].text == "simple paragraph"
