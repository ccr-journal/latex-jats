import xml.etree.ElementTree as ET
from latex_jats.convert import fix_footnotes


def _make_doc(body_content, back_content=""):
    return f"<article><body>{body_content}</body><back>{back_content}</back></article>"


def test_inline_fn_replaced_with_xref(xml_file):
    xml = _make_doc("""\
<sec>
  <p>Some text<fn id="fn1"><p id="footnote1">Footnote text.</p></fn> more text.</p>
</sec>""")
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    # <fn> should be gone from <p>
    p = root.find(".//sec/p")
    assert p.find("fn") is None
    # <xref> should be in its place
    xref = p.find("xref")
    assert xref is not None
    assert xref.get("rid") == "fn1"
    assert xref.get("ref-type") == "fn"
    assert xref.text == "1"


def test_fn_moved_to_fn_group_in_back(xml_file):
    xml = _make_doc("""\
<sec>
  <p>Text<fn id="fn1"><p id="footnote1">Note.</p></fn>.</p>
</sec>""")
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    fn_group = root.find(".//back/fn-group")
    assert fn_group is not None
    fn = fn_group.find("fn")
    assert fn is not None
    assert fn.get("id") == "fn1"


def test_no_footnotes_no_xrefs(xml_file):
    xml = _make_doc("<sec><p>Simple paragraph.</p></sec>")
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    # no inline footnotes means no <xref> should have been inserted
    assert root.find(".//sec/p/xref") is None
    # any fn-group that was created should be empty
    fn_group = root.find(".//back/fn-group")
    if fn_group is not None:
        assert list(fn_group) == []
