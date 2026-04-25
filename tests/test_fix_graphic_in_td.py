import logging
import xml.etree.ElementTree as ET

import pytest

from jatsmith.convert import fix_graphic_in_td, fix_pdf_graphic_refs

XLINK = "http://www.w3.org/1999/xlink"

DOC = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <sec>
      <table-wrap id="T1"><table><tbody>
{row}
      </tbody></table></table-wrap>
    </sec>
  </body>
</article>"""


def _cell(xml):
    return "<tr>" + xml + "</tr>"


def test_graphic_in_p_in_td_renamed(xml_file):
    xml = DOC.format(row=_cell(
        '<td><p><graphic xlink:href="fig.svg"/></p>'
        '<p><italic>Caption</italic></p></td>'
    ))
    path = xml_file(xml)
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    td = root.find(".//td")
    assert td.find("p/graphic") is None
    ig = td.find("p/inline-graphic")
    assert ig is not None
    assert ig.get(f"{{{XLINK}}}href") == "fig.svg"
    # <p> wrapper preserved; caption <p> left untouched
    assert len(td.findall("p")) == 2


def test_graphic_directly_in_td_renamed(xml_file):
    xml = DOC.format(row=_cell('<td><graphic xlink:href="fig.png"/></td>'))
    path = xml_file(xml)
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    td = root.find(".//td")
    assert td.find("graphic") is None
    assert td.find("inline-graphic") is not None


def test_graphic_in_th_renamed(xml_file):
    xml = DOC.format(row=(
        '<tr><th><p><graphic xlink:href="head.png"/></p></th></tr>'
    ))
    path = xml_file(xml)
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    th = root.find(".//th")
    assert th.find("p/graphic") is None
    assert th.find("p/inline-graphic") is not None


def test_graphic_outside_cells_untouched(xml_file):
    xml = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <fig id="F1"><graphic xlink:href="body.svg"/></fig>
    <p><graphic xlink:href="loose.svg"/></p>
  </body>
</article>"""
    path = xml_file(xml)
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    assert root.find(".//fig/graphic") is not None
    assert root.find(".//fig/inline-graphic") is None
    assert root.find(".//body/p/graphic") is not None


def test_multiple_graphics_in_cell_all_renamed(xml_file):
    xml = DOC.format(row=_cell(
        '<td>'
        '<p><graphic xlink:href="a.svg"/></p>'
        '<p><graphic xlink:href="b.svg"/></p>'
        '</td>'
    ))
    path = xml_file(xml)
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    td = root.find(".//td")
    assert td.findall("p/graphic") == []
    igs = td.findall("p/inline-graphic")
    assert len(igs) == 2
    assert {ig.get(f"{{{XLINK}}}href") for ig in igs} == {"a.svg", "b.svg"}


def test_warning_logged_per_rewrite(xml_file, caplog: pytest.LogCaptureFixture):
    xml = DOC.format(row=_cell(
        '<td>'
        '<p><graphic xlink:href="a.svg"/></p>'
        '<p><graphic xlink:href="b.svg"/></p>'
        '</td>'
    ))
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING, logger="jatsmith.convert"):
        fix_graphic_in_td(path)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all("inline-graphic" in r.getMessage() for r in warnings)
    hrefs = {w.getMessage().split("href=")[1].split(")")[0] for w in warnings}
    assert hrefs == {"a.svg", "b.svg"}


def test_no_change_when_no_graphic_in_cells(xml_file):
    xml = DOC.format(row=_cell('<td><p>plain text</p></td>'))
    path = xml_file(xml)
    # Should not raise; file may or may not be rewritten, but content is preserved.
    fix_graphic_in_td(path)

    root = ET.parse(path).getroot()
    assert root.find(".//td/p").text == "plain text"


def test_fix_pdf_graphic_refs_handles_inline_graphic(xml_file):
    """Regression guard: downstream graphic passes must see <inline-graphic> too."""
    xml = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <fig id="F1"><graphic xlink:href="body.pdf"/></fig>
    <table-wrap id="T1"><table><tbody><tr>
      <td><p><inline-graphic xlink:href="cell.pdf"/></p></td>
    </tr></tbody></table></table-wrap>
  </body>
</article>"""
    path = xml_file(xml)
    fix_pdf_graphic_refs(path)

    root = ET.parse(path).getroot()
    assert root.find(".//fig/graphic").get(f"{{{XLINK}}}href") == "body.svg"
    assert root.find(".//td//inline-graphic").get(f"{{{XLINK}}}href") == "cell.svg"
