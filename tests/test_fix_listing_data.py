import base64
import xml.etree.ElementTree as ET

from latex_jats.convert import fix_listing_data

LTX_NS = "http://dlmf.nist.gov/LaTeXML"
LTX = f"{{{LTX_NS}}}"

ET.register_namespace("ltx", LTX_NS)

MINIMAL_DOC = f"""\
<?xml version="1.0" encoding="utf-8"?>
<ltx:document xmlns:ltx="{LTX_NS}">
  {{listing}}
</ltx:document>"""


def _b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_base64_listing_replaced_with_plain_text(xml_file):
    raw_text = "\u201cHello\u201d\nCount \u2265 10\nDone"
    listing_xml = (
        f'<ltx:listing xmlns:ltx="{LTX_NS}" '
        f'data="{_b64(raw_text)}" dataencoding="base64" datamimetype="text/plain">'
        f"<ltx:listingline><ltx:text>broken</ltx:text></ltx:listingline>"
        f"</ltx:listing>"
    )
    path = xml_file(MINIMAL_DOC.format(listing=listing_xml))
    fix_listing_data(path)

    root = ET.parse(path).getroot()
    listing = root.find(f".//{LTX}listing")
    assert listing is not None

    lines = listing.findall(f"{LTX}listingline")
    assert len(lines) == 3
    assert lines[0].text == "\u201cHello\u201d"
    assert lines[1].text == "Count \u2265 10"
    assert lines[2].text == "Done"
    # No nested elements inside listinglines
    for ll in lines:
        assert list(ll) == []


def test_listing_without_data_unchanged(xml_file):
    listing_xml = (
        f'<ltx:listing xmlns:ltx="{LTX_NS}">'
        f"<ltx:listingline>plain text</ltx:listingline>"
        f"</ltx:listing>"
    )
    path = xml_file(MINIMAL_DOC.format(listing=listing_xml))
    fix_listing_data(path)

    root = ET.parse(path).getroot()
    listing = root.find(f".//{LTX}listing")
    lines = listing.findall(f"{LTX}listingline")
    assert len(lines) == 1
    assert lines[0].text == "plain text"


def test_empty_data_unchanged(xml_file):
    listing_xml = (
        f'<ltx:listing xmlns:ltx="{LTX_NS}" '
        f'data="" dataencoding="base64" datamimetype="text/plain">'
        f"<ltx:listingline>original</ltx:listingline>"
        f"</ltx:listing>"
    )
    path = xml_file(MINIMAL_DOC.format(listing=listing_xml))
    fix_listing_data(path)

    root = ET.parse(path).getroot()
    listing = root.find(f".//{LTX}listing")
    lines = listing.findall(f"{LTX}listingline")
    assert len(lines) == 1
    assert lines[0].text == "original"


def test_trailing_newline_not_extra_line(xml_file):
    raw_text = "line1\nline2\n"
    listing_xml = (
        f'<ltx:listing xmlns:ltx="{LTX_NS}" '
        f'data="{_b64(raw_text)}" dataencoding="base64" datamimetype="text/plain">'
        f"<ltx:listingline>old</ltx:listingline>"
        f"</ltx:listing>"
    )
    path = xml_file(MINIMAL_DOC.format(listing=listing_xml))
    fix_listing_data(path)

    root = ET.parse(path).getroot()
    listing = root.find(f".//{LTX}listing")
    lines = listing.findall(f"{LTX}listingline")
    assert len(lines) == 2
    assert lines[0].text == "line1"
    assert lines[1].text == "line2"
