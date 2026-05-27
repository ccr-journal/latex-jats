import xml.etree.ElementTree as ET

from jatsmith.convert import convert_ack_to_sec


def _doc(body_content, back_content):
    return f"<article><body>{body_content}</body><back>{back_content}</back></article>"


def test_ack_in_back_converted_to_trailing_sec_in_body(xml_file):
    xml = _doc(
        "<sec id='S1'><title>Intro</title><p>Hello.</p></sec>",
        "<ack><p>Thanks.</p></ack><fn-group><title>Notes</title><fn id='fn1'><p>Note.</p></fn></fn-group>",
    )
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    body = root.find("body")
    back = root.find("back")

    assert back.find("ack") is None
    assert body.find("ack") is None
    assert back.find("fn-group") is not None

    last = list(body)[-1]
    assert last.tag == "sec"
    assert last.get("id") == "ack"
    assert last.find("title").text == "Acknowledgements"
    assert last.find("p").text == "Thanks."


def test_ack_already_in_body_is_also_converted(xml_file):
    xml = _doc(
        "<sec id='S1'><p>Hi.</p></sec><ack id='a1'><p>Thanks.</p></ack>",
        "<fn-group/>",
    )
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    body = root.find("body")
    assert body.find("ack") is None
    secs = body.findall("sec")
    assert secs[-1].get("id") == "a1"
    assert secs[-1].find("title").text == "Acknowledgements"


def test_existing_ack_title_is_preserved(xml_file):
    xml = _doc(
        "<sec><p>Hi.</p></sec>",
        "<ack id='a1'><title>Funding and thanks</title><p>Thanks.</p></ack>",
    )
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    sec = root.find("body/sec[@id='a1']")
    assert sec is not None
    assert sec.find("title").text == "Funding and thanks"
    assert len(sec.findall("title")) == 1


def test_no_ack_is_noop(xml_file):
    xml = _doc("<sec><p>Hello.</p></sec>", "<fn-group/>")
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    assert root.find("body/ack") is None
    assert root.find("back/ack") is None
    assert root.find("back/fn-group") is not None


def test_multiple_acks_all_converted(xml_file):
    xml = _doc(
        "<sec><p>Hi.</p></sec>",
        "<ack id='a1'><p>A.</p></ack><ack id='a2'><p>B.</p></ack>",
    )
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    assert root.find("back/ack") is None
    secs = root.findall("body/sec")
    ack_secs = [s for s in secs if s.get("id") in ("a1", "a2")]
    assert [s.get("id") for s in ack_secs] == ["a1", "a2"]
    for s in ack_secs:
        assert s.find("title").text == "Acknowledgements"


def test_sig_block_remains_last(xml_file):
    xml = _doc(
        "<sec><p>Hi.</p></sec><sig-block><sig>Signed.</sig></sig-block>",
        "<ack id='a1'><p>Thanks.</p></ack>",
    )
    path = xml_file(xml)
    convert_ack_to_sec(path)

    root = ET.parse(path).getroot()
    body = root.find("body")
    children = list(body)
    assert children[-1].tag == "sig-block"
    assert children[-2].tag == "sec"
    assert children[-2].get("id") == "a1"
