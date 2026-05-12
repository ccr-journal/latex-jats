import xml.etree.ElementTree as ET

from jatsmith.convert import move_ack_to_body


def _doc(body_content, back_content):
    return f"<article><body>{body_content}</body><back>{back_content}</back></article>"


def test_ack_moved_from_back_to_end_of_body(xml_file):
    xml = _doc(
        "<sec id='S1'><title>Intro</title><p>Hello.</p></sec>",
        "<ack><p>Thanks.</p></ack><fn-group><title>Notes</title><fn id='fn1'><p>Note.</p></fn></fn-group>",
    )
    path = xml_file(xml)
    move_ack_to_body(path)

    root = ET.parse(path).getroot()
    body = root.find("body")
    back = root.find("back")

    assert back.find("ack") is None
    assert back.find("fn-group") is not None

    body_children = list(body)
    assert body_children[-1].tag == "ack"
    assert body_children[-1].find("p").text == "Thanks."


def test_no_ack_is_noop(xml_file):
    xml = _doc("<sec><p>Hello.</p></sec>", "<fn-group/>")
    path = xml_file(xml)
    move_ack_to_body(path)

    root = ET.parse(path).getroot()
    assert root.find("body/ack") is None
    assert root.find("back/fn-group") is not None


def test_multiple_acks_all_moved(xml_file):
    xml = _doc(
        "<sec><p>Hi.</p></sec>",
        "<ack id='a1'><p>A.</p></ack><ack id='a2'><p>B.</p></ack>",
    )
    path = xml_file(xml)
    move_ack_to_body(path)

    root = ET.parse(path).getroot()
    assert root.find("back/ack") is None
    moved = root.findall("body/ack")
    assert [a.get("id") for a in moved] == ["a1", "a2"]
