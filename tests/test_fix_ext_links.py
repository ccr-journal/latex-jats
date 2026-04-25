import xml.etree.ElementTree as ET

from jatsmith.convert import fix_ext_links

XLINK = "http://www.w3.org/1999/xlink"


def _make_doc(body_content):
    return (
        f'<article xmlns:xlink="{XLINK}">'
        f"<body>{body_content}</body></article>"
    )


def test_adds_uri_type_when_missing(xml_file):
    path = xml_file(_make_doc(
        '<p><ext-link xlink:href="https://osf.io/abc">https://osf.io/abc</ext-link></p>'
    ))
    fix_ext_links(path)
    root = ET.parse(path).getroot()
    el = root.find(".//ext-link")
    assert el.get("ext-link-type") == "uri"


def test_preserves_existing_doi_type(xml_file):
    path = xml_file(_make_doc(
        '<p><ext-link ext-link-type="doi" xlink:href="https://doi.org/10.1234/x">'
        "https://doi.org/10.1234/x</ext-link></p>"
    ))
    fix_ext_links(path)
    root = ET.parse(path).getroot()
    el = root.find(".//ext-link")
    assert el.get("ext-link-type") == "doi"


def test_mixed_links(xml_file):
    path = xml_file(_make_doc(
        '<p>'
        '<ext-link xlink:href="https://osf.io/abc">osf</ext-link> '
        '<ext-link ext-link-type="doi" xlink:href="https://doi.org/10.1234/x">doi</ext-link> '
        '<ext-link xlink:href="https://github.com/x">gh</ext-link>'
        '</p>'
    ))
    fix_ext_links(path)
    root = ET.parse(path).getroot()
    links = root.findall(".//ext-link")
    assert links[0].get("ext-link-type") == "uri"
    assert links[1].get("ext-link-type") == "doi"
    assert links[2].get("ext-link-type") == "uri"
