import logging

from jatsmith.convert import warn_section_acknowledgements

MINIMAL_DOC = """\
<article>
  <body>
    {sec}
  </body>
</article>"""


def _sec(title):
    return f"<sec><title>{title}</title><p>body</p></sec>"


def test_acknowledgements_section_warns(xml_file, caplog):
    path = xml_file(MINIMAL_DOC.format(sec=_sec("Acknowledgements")))
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 1
    assert "Acknowledgements" in caplog.records[0].message
    assert "\\acknowledgements" in caplog.records[0].message


def test_us_spelling_also_warns(xml_file, caplog):
    path = xml_file(MINIMAL_DOC.format(sec=_sec("Acknowledgments")))
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 1
    assert "Acknowledgments" in caplog.records[0].message


def test_singular_also_warns(xml_file, caplog):
    path = xml_file(MINIMAL_DOC.format(sec=_sec("Acknowledgement")))
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 1


def test_case_insensitive(xml_file, caplog):
    path = xml_file(MINIMAL_DOC.format(sec=_sec("ACKNOWLEDGEMENTS")))
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 1


def test_other_sections_do_not_warn(xml_file, caplog):
    path = xml_file(MINIMAL_DOC.format(sec=_sec("Introduction")))
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 0


def test_no_body_is_noop(xml_file, caplog):
    path = xml_file("<article><front/></article>")
    with caplog.at_level(logging.WARNING):
        warn_section_acknowledgements(path)
    assert len(caplog.records) == 0
