import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import fix_fig_group_structure

XLINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'

MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      {content}
    </sec>
  </body>
</article>"""


def _fig_group(root):
    return root.find(".//fig-group")


def test_bare_graphic_children_are_wrapped(xml_file, caplog):
    fg = (
        f'<fig-group id="FG1">'
        f'<graphic {XLINK} xlink:href="a.png"/>'
        f'<graphic {XLINK} xlink:href="b.png"/>'
        f'</fig-group>'
    )
    path = xml_file(MINIMAL_DOC.format(content=fg))
    with caplog.at_level(logging.INFO):
        fix_fig_group_structure(path)

    fig_group = _fig_group(ET.parse(path).getroot())
    children = list(fig_group)
    assert [c.tag for c in children] == ["fig", "fig"]
    assert children[0].get("id") == "FG1.sf1"
    assert children[1].get("id") == "FG1.sf2"
    assert children[0].find("graphic") is not None
    assert children[1].find("graphic") is not None
    assert sum(1 for r in caplog.records if r.levelno == logging.INFO) == 2


def test_p_wrapped_graphic_children_are_wrapped(xml_file, caplog):
    fg = (
        f'<fig-group id="FG1">'
        f'<p><graphic {XLINK} xlink:href="a.png"/></p>'
        f'<p><graphic {XLINK} xlink:href="b.png"/></p>'
        f'</fig-group>'
    )
    path = xml_file(MINIMAL_DOC.format(content=fg))
    with caplog.at_level(logging.INFO):
        fix_fig_group_structure(path)

    fig_group = _fig_group(ET.parse(path).getroot())
    children = list(fig_group)
    assert [c.tag for c in children] == ["fig", "fig"]
    # the stray <p> is gone — the <graphic> is now a direct child of <fig>
    assert [c.tag for c in children[0]] == ["graphic"]
    assert [c.tag for c in children[1]] == ["graphic"]


def test_righ_shape_unchanged(xml_file, caplog):
    fg = (
        f'<fig-group id="FG1">'
        f'<fig id="FG1.sub1"><label>(a)</label><caption><p>Left</p></caption>'
        f'<graphic {XLINK} xlink:href="a.png"/></fig>'
        f'<fig id="FG1.sub2"><label>(b)</label><caption><p>Right</p></caption>'
        f'<graphic {XLINK} xlink:href="b.png"/></fig>'
        f'</fig-group>'
    )
    path = xml_file(MINIMAL_DOC.format(content=fg))
    with caplog.at_level(logging.INFO):
        fix_fig_group_structure(path)

    fig_group = _fig_group(ET.parse(path).getroot())
    children = list(fig_group)
    assert [c.tag for c in children] == ["fig", "fig"]
    assert [c.get("id") for c in children] == ["FG1.sub1", "FG1.sub2"]
    assert caplog.records == []


def test_missing_group_id_falls_back(xml_file, caplog):
    fg = (
        f'<fig-group>'
        f'<graphic {XLINK} xlink:href="a.png"/>'
        f'</fig-group>'
    )
    path = xml_file(MINIMAL_DOC.format(content=fg))
    with caplog.at_level(logging.INFO):
        fix_fig_group_structure(path)

    fig_group = _fig_group(ET.parse(path).getroot())
    inner = list(fig_group)[0]
    assert inner.tag == "fig"
    assert inner.get("id") == "figgroup.sf1"


def test_mixed_children_only_bare_are_wrapped(xml_file, caplog):
    fg = (
        f'<fig-group id="FG1">'
        f'<fig id="orig"><label>(a)</label><caption><p>Already done</p></caption>'
        f'<graphic {XLINK} xlink:href="a.png"/></fig>'
        f'<graphic {XLINK} xlink:href="b.png"/>'
        f'</fig-group>'
    )
    path = xml_file(MINIMAL_DOC.format(content=fg))
    with caplog.at_level(logging.INFO):
        fix_fig_group_structure(path)

    children = list(_fig_group(ET.parse(path).getroot()))
    assert [c.tag for c in children] == ["fig", "fig"]
    assert children[0].get("id") == "orig"
    # second child is the wrapped synthetic; index is 1 (1-based, first wrap in this group)
    assert children[1].get("id") == "FG1.sf1"
    assert sum(1 for r in caplog.records if r.levelno == logging.INFO) == 1
