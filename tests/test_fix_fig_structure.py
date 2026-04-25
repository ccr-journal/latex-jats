import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import fix_fig_structure

MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      {content}
    </sec>
  </body>
</article>"""


KNOWN_GOOD = (
    '<fig id="F1">'
    '<label>Figure 1:</label>'
    '<caption><p>A title</p></caption>'
    '<graphic xlink:href="fig1.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
    '</fig>'
)


def _fig_tags(root):
    fig = root.find(".//fig")
    return [c.tag for c in fig]


def test_known_good_unchanged(xml_file, caplog):
    xml = MINIMAL_DOC.format(content=KNOWN_GOOD)
    path = xml_file(xml)
    with caplog.at_level(logging.INFO):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["label", "caption", "graphic"]
    assert caplog.records == []


def test_bare_p_graphic_is_unwrapped(xml_file, caplog):
    fig = (
        '<fig id="F2">'
        '<label>Figure 2:</label>'
        '<caption><p>Another title</p></caption>'
        '<p><graphic xlink:href="fig2.png" xmlns:xlink="http://www.w3.org/1999/xlink"/></p>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.INFO):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["label", "caption", "graphic"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.INFO
    assert "F2" in caplog.records[0].message
    assert "makebox" in caplog.records[0].message


def test_graphic_in_p_outside_fig_is_ignored(xml_file, caplog):
    content = '<p><graphic xlink:href="x.png" xmlns:xlink="http://www.w3.org/1999/xlink"/></p>'
    xml = MINIMAL_DOC.format(content=content)
    path = xml_file(xml)
    with caplog.at_level(logging.INFO):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    sec = root.find(".//sec")
    ps = sec.findall("p")
    assert len(ps) == 1
    assert ps[0].find("graphic") is not None
    assert caplog.records == []


def test_mixed_p_content_warns(xml_file, caplog):
    fig = (
        '<fig id="F3">'
        '<label>Figure 3:</label>'
        '<caption><p>t</p></caption>'
        '<p>caption-like text<graphic xlink:href="f.png" xmlns:xlink="http://www.w3.org/1999/xlink"/></p>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    # Unchanged
    assert _fig_tags(root) == ["label", "caption", "p"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "F3" in caplog.records[0].message


def test_two_graphics_in_one_p_warns(xml_file, caplog):
    fig = (
        '<fig id="F4">'
        '<label>Figure 4:</label>'
        '<caption><p>t</p></caption>'
        '<p>'
        '<graphic xlink:href="a.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '<graphic xlink:href="b.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '</p>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["label", "caption", "p"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "F4" in caplog.records[0].message


def test_extra_sibling_after_graphic_warns(xml_file, caplog):
    fig = (
        '<fig id="F5">'
        '<label>Figure 5:</label>'
        '<caption><p>t</p></caption>'
        '<graphic xlink:href="f.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '<p>stray prose</p>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["label", "caption", "graphic", "p"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "F5" in caplog.records[0].message


def test_caption_with_extra_children_warns(xml_file, caplog):
    fig = (
        '<fig id="F6">'
        '<label>Figure 6:</label>'
        '<caption><p>t</p><p>extra caption prose</p></caption>'
        '<graphic xlink:href="f.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["label", "caption", "graphic"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "F6" in caplog.records[0].message
    assert "caption" in caplog.records[0].message


def test_nested_subfig_warns(xml_file, caplog):
    """A <fig> inside another <fig> (subfigure) hasn't been confirmed to render
    — both the outer and inner deviate from the known-good shape and should warn."""
    fig = (
        '<fig id="F_outer">'
        '<label>Figure 1:</label>'
        '<caption><p>outer</p></caption>'
        '<fig id="F_inner"><graphic xlink:href="sub.png" xmlns:xlink="http://www.w3.org/1999/xlink"/></fig>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    messages = [r.message for r in caplog.records]
    assert any("F_outer" in m for m in messages)
    assert any("F_inner" in m for m in messages)


def test_listing_fig_warns(xml_file, caplog):
    """<fig fig-type="listing"> with <code> instead of <graphic> does not render at
    Ingenta (confirmed with FOOT article) — warn so author/editor knows."""
    fig = (
        '<fig fig-type="listing" id="LST1">'
        '<label>Listing 1:</label>'
        '<caption><p>a listing</p></caption>'
        '<code>print("hello")</code>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "LST1" in caplog.records[0].message


def test_missing_label_warns(xml_file, caplog):
    fig = (
        '<fig id="F7">'
        '<caption><p>t</p></caption>'
        '<graphic xlink:href="f.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '</fig>'
    )
    xml = MINIMAL_DOC.format(content=fig)
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        fix_fig_structure(path)

    root = ET.parse(path).getroot()
    assert _fig_tags(root) == ["caption", "graphic"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "F7" in caplog.records[0].message
    assert "label" in caplog.records[0].message
