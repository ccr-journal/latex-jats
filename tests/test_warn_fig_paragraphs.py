import xml.etree.ElementTree as ET

import pytest

from latex_jats.convert import warn_fig_paragraphs

MINIMAL_DOC = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <sec>
      {fig}
    </sec>
  </body>
</article>"""


def test_stray_period_triggers_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        fig="""\
<fig id="fig1">
  <label>Figure 1:</label>
  <graphic xlink:href="img.png"/>
  <p>.</p>
</fig>"""
    )
    path = xml_file(xml)
    with caplog.at_level("WARNING"):
        warn_fig_paragraphs(path)
    assert any("fig1" in r.message and "." in r.message for r in caplog.records)


def test_stray_punctuation_triggers_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        fig="""\
<fig id="fig2">
  <graphic xlink:href="img.png"/>
  <p>, .</p>
</fig>"""
    )
    path = xml_file(xml)
    with caplog.at_level("WARNING"):
        warn_fig_paragraphs(path)
    assert any("fig2" in r.message for r in caplog.records)


def test_p_with_real_text_no_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        fig="""\
<fig id="fig3">
  <graphic xlink:href="img.png"/>
  <p>Source: Author calculations.</p>
</fig>"""
    )
    path = xml_file(xml)
    with caplog.at_level("WARNING"):
        warn_fig_paragraphs(path)
    assert not any("fig3" in r.message for r in caplog.records)


def test_fig_without_p_no_warning(xml_file, caplog):
    xml = MINIMAL_DOC.format(
        fig="""\
<fig id="fig4">
  <label>Figure 4:</label>
  <graphic xlink:href="img.png"/>
</fig>"""
    )
    path = xml_file(xml)
    with caplog.at_level("WARNING"):
        warn_fig_paragraphs(path)
    assert not caplog.records


def test_xml_not_modified(xml_file):
    """warn_fig_paragraphs must not alter the XML file."""
    xml = MINIMAL_DOC.format(
        fig="""\
<fig id="fig5">
  <graphic xlink:href="img.png"/>
  <p>.</p>
</fig>"""
    )
    path = xml_file(xml)
    before = open(path).read()
    warn_fig_paragraphs(path)
    after = open(path).read()
    assert before == after
