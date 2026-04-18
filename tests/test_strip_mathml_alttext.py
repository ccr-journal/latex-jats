import xml.etree.ElementTree as ET

from latex_jats.convert import strip_mathml_alttext

MML = "http://www.w3.org/1998/Math/MathML"


def _make_doc(body_content):
    return (
        f'<article xmlns:mml="{MML}">'
        f"<body>{body_content}</body></article>"
    )


def test_removes_alttext_with_less_than(xml_file):
    path = xml_file(_make_doc(
        '<p><inline-formula><mml:math id="m1" alttext="&lt;4" display="inline">'
        '<mml:mrow><mml:mi/><mml:mo>&lt;</mml:mo><mml:mn>4</mml:mn></mml:mrow>'
        '</mml:math></inline-formula></p>'
    ))
    strip_mathml_alttext(path)
    root = ET.parse(path).getroot()
    math = root.find(f".//{{{MML}}}math")
    assert "alttext" not in math.attrib
    # other attributes and child structure preserved
    assert math.get("id") == "m1"
    assert math.get("display") == "inline"
    mo = math.find(f".//{{{MML}}}mo")
    assert mo.text == "<"


def test_removes_alttext_without_special_chars(xml_file):
    path = xml_file(_make_doc(
        '<p><inline-formula><mml:math id="m1" alttext="\\kappa" display="inline">'
        '<mml:mi>κ</mml:mi></mml:math></inline-formula></p>'
    ))
    strip_mathml_alttext(path)
    root = ET.parse(path).getroot()
    math = root.find(f".//{{{MML}}}math")
    assert "alttext" not in math.attrib
    assert math.get("id") == "m1"


def test_no_op_when_alttext_absent(xml_file):
    path = xml_file(_make_doc(
        '<p><inline-formula><mml:math id="m1" display="inline">'
        '<mml:mi>x</mml:mi></mml:math></inline-formula></p>'
    ))
    strip_mathml_alttext(path)
    root = ET.parse(path).getroot()
    math = root.find(f".//{{{MML}}}math")
    assert "alttext" not in math.attrib
    assert math.get("id") == "m1"


def test_multiple_math_elements(xml_file):
    path = xml_file(_make_doc(
        '<p>'
        '<inline-formula><mml:math id="m1" alttext="p&lt;.01"><mml:mi>p</mml:mi></mml:math></inline-formula>'
        '<inline-formula><mml:math id="m2" alttext="&gt;10"><mml:mn>10</mml:mn></mml:math></inline-formula>'
        '<inline-formula><mml:math id="m3" alttext="\\alpha"><mml:mi>α</mml:mi></mml:math></inline-formula>'
        '</p>'
    ))
    strip_mathml_alttext(path)
    root = ET.parse(path).getroot()
    for math in root.iter(f"{{{MML}}}math"):
        assert "alttext" not in math.attrib
