import xml.etree.ElementTree as ET

from jatsmith.convert import fix_footnotes


def _make_doc(body_content, back_content=""):
    return f"<article><body>{body_content}</body><back>{back_content}</back></article>"


def test_inline_fn_replaced_with_xref(xml_file):
    xml = _make_doc(
        """\
<sec>
  <p>Some text<fn id="fn1"><p id="footnote1">Footnote text.</p></fn> more text.</p>
</sec>"""
    )
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    # <fn> should be gone from <p>
    p = root.find(".//sec/p")
    assert p is not None
    assert p.find("fn") is None
    # <xref> should be in its place
    xref = p.find("xref")
    assert xref is not None
    assert xref.get("rid") == "fn1"
    assert xref.get("ref-type") == "fn"
    assert xref.get("specific-use") == "fn"
    sup = xref.find("sup")
    assert sup is not None
    assert sup.text == "1"
    # tail text after the footnote marker must be preserved
    assert xref.tail == " more text."


def test_fn_moved_to_fn_group_in_back(xml_file):
    xml = _make_doc(
        """\
<sec>
  <p>Text<fn id="fn1"><p id="footnote1">Note.</p></fn>.</p>
</sec>"""
    )
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    fn_group = root.find(".//back/fn-group")
    assert fn_group is not None
    title = fn_group.find("title")
    assert title is not None
    assert title.text == "Notes"
    fn = fn_group.find("fn")
    assert fn is not None
    assert fn.get("id") == "fn1"
    assert fn.get("symbol") == "1"


def test_fn_group_placed_before_ref_list(xml_file):
    xml = _make_doc(
        """\
<sec>
  <p>Text<fn id="fn1"><p id="footnote1">Note.</p></fn>.</p>
</sec>""",
        '<ref-list><ref id="r1"><mixed-citation>Ref</mixed-citation></ref></ref-list>',
    )
    path = xml_file(xml)
    fix_footnotes(path)

    root = ET.parse(path).getroot()
    back = root.find(".//back")
    children = list(back)
    fn_group_idx = next(i for i, c in enumerate(children) if c.tag == "fn-group")
    ref_list_idx = next(i for i, c in enumerate(children) if c.tag == "ref-list")
    assert fn_group_idx < ref_list_idx


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
        assert list(fn_group) == []
