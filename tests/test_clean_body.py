import xml.etree.ElementTree as ET
from latex_jats.convert import clean_body


def _make_doc(body_content):
    return f"<article><body>{body_content}</body></article>"


def test_empty_p_removed(xml_file):
    path = xml_file(_make_doc("<p></p><sec><title>Intro</title><p>Content.</p></sec>"))
    clean_body(path)
    root = ET.parse(path).getroot()
    body = root.find(".//body")
    # empty <p> at body level should be gone
    assert body.find("p") is None


def test_content_p_kept(xml_file):
    path = xml_file(_make_doc("<sec><title>Intro</title><p>Hello world.</p></sec>"))
    clean_body(path)
    root = ET.parse(path).getroot()
    p = root.find(".//sec/p")
    assert p is not None
    assert p.text == "Hello world."


def test_title_directly_in_body_removed(xml_file):
    path = xml_file(_make_doc("<title>Bad Title</title><sec><title>Good</title></sec>"))
    clean_body(path)
    root = ET.parse(path).getroot()
    body = root.find(".//body")
    # direct <title> child of <body> should be removed
    assert body.find("title") is None
    # but <title> inside <sec> should remain
    assert root.find(".//sec/title") is not None
