import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import warn_tfoot_notes

MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      {table_wrap}
    </sec>
  </body>
</article>"""


def test_tfoot_emits_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        table_wrap="""\
<table-wrap id="T1">
  <table>
    <tbody><tr><td>data</td></tr></tbody>
    <tfoot><tr><th colspan="1">Standard errors in parentheses</th></tr></tfoot>
  </table>
</table-wrap>"""
    )
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        warn_tfoot_notes(path)

    assert len(caplog.records) == 1
    assert "T1" in caplog.records[0].message
    assert "tabular" in caplog.records[0].message


def test_no_tfoot_no_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        table_wrap="""\
<table-wrap id="T1">
  <table>
    <tbody><tr><td>data</td></tr></tbody>
  </table>
</table-wrap>"""
    )
    path = xml_file(xml)
    with caplog.at_level(logging.WARNING):
        warn_tfoot_notes(path)

    assert len(caplog.records) == 0
