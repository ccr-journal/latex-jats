import xml.etree.ElementTree as ET

from jatsmith.convert import (
    _decompose_math_alphanumeric,
    normalize_mathml_chars,
)

MML = "http://www.w3.org/1998/Math/MathML"


def _make_doc(body_content):
    return (
        f'<article xmlns:mml="{MML}">'
        f"<body>{body_content}</body></article>"
    )


def test_decompose_bold_capital_latin():
    assert _decompose_math_alphanumeric("\U0001D400") == ("bold", "A")


def test_decompose_bold_italic_small_latin():
    assert _decompose_math_alphanumeric("\U0001D498") == ("bold-italic", "w")


def test_decompose_bold_italic_greek_small():
    assert _decompose_math_alphanumeric("\U0001D737") == ("bold-italic", "β")


def test_decompose_bold_script_capital():
    assert _decompose_math_alphanumeric("\U0001D4D0") == ("bold-script", "A")


def test_decompose_double_struck_capital():
    assert _decompose_math_alphanumeric("\U0001D538") == ("double-struck", "A")


def test_decompose_fraktur_capital():
    assert _decompose_math_alphanumeric("\U0001D504") == ("fraktur", "A")


def test_decompose_bold_digit():
    assert _decompose_math_alphanumeric("\U0001D7CE") == ("bold", "0")


def test_decompose_monospace_capital():
    assert _decompose_math_alphanumeric("\U0001D670") == ("monospace", "A")


def test_decompose_digamma():
    assert _decompose_math_alphanumeric("\U0001D7CA") == ("bold", "\u03DC")


def test_decompose_epsilon_symbol():
    assert _decompose_math_alphanumeric("\U0001D6DC") == ("bold", "\u03F5")


def test_decompose_plain_char_is_noop():
    assert _decompose_math_alphanumeric("A") is None
    assert _decompose_math_alphanumeric("β") is None


def test_rewrites_single_char_mi_with_mathvariant(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math><mml:mi>\U0001D498</mml:mi></mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mi = root.find(f".//{{{MML}}}mi")
    assert mi.text == "w"
    assert mi.get("mathvariant") == "bold-italic"


def test_rewrites_greek_bold_italic(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math><mml:mi>\U0001D737</mml:mi></mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mi = root.find(f".//{{{MML}}}mi")
    assert mi.text == "β"
    assert mi.get("mathvariant") == "bold-italic"


def test_rewrites_digit_in_mn(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math><mml:mn>\U0001D7CE</mml:mn></mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mn = root.find(f".//{{{MML}}}mn")
    assert mn.text == "0"
    assert mn.get("mathvariant") == "bold"


def test_preserves_existing_mathvariant(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math>'
        '<mml:mi mathvariant="italic">\U0001D498</mml:mi>'
        '</mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mi = root.find(f".//{{{MML}}}mi")
    assert mi.text == "w"
    assert mi.get("mathvariant") == "italic"


def test_multiple_math_chars_substituted_without_mathvariant(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math><mml:mi>\U0001D498\U0001D499</mml:mi></mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mi = root.find(f".//{{{MML}}}mi")
    assert mi.text == "wx"
    assert mi.get("mathvariant") is None


def test_rewrites_chars_in_plain_text(xml_file):
    path = xml_file(_make_doc(
        "<p>The vector \U0001D498 is used.</p>"
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    p = root.find(".//p")
    assert p.text == "The vector w is used."


def test_rewrites_chars_in_tail(xml_file):
    path = xml_file(_make_doc(
        "<p><italic>italicised</italic> \U0001D498 stuff</p>"
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    italic = root.find(".//italic")
    assert italic.tail == " w stuff"


def test_noop_when_no_math_chars(xml_file):
    path = xml_file(_make_doc(
        '<p><mml:math><mml:mi>w</mml:mi></mml:math></p>'
    ))
    normalize_mathml_chars(path)
    root = ET.parse(path).getroot()
    mi = root.find(f".//{{{MML}}}mi")
    assert mi.text == "w"
    assert mi.get("mathvariant") is None
