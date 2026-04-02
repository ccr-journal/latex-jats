import xml.etree.ElementTree as ET

from latex_jats.convert import fix_disp_formula_in_list_item

MINIMAL_DOC = """\
<article>
  <body>
    <sec>
      <list list-type="simple">
        {list_item}
      </list>
    </sec>
  </body>
</article>"""


def test_disp_formula_wrapped_in_p(xml_file):
    xml = MINIMAL_DOC.format(
        list_item="""\
<list-item id="i1">
  <p id="i1.p1">Some text.</p>
  <disp-formula id="EQ1"><mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"/></disp-formula>
</list-item>"""
    )
    path = xml_file(xml)
    fix_disp_formula_in_list_item(path)

    root = ET.parse(path).getroot()
    li = root.find(".//list-item")
    assert li is not None

    # <disp-formula> must not be a direct child of <list-item>
    assert li.find("disp-formula") is None

    # <disp-formula> must now be inside a <p> inside <list-item>
    p_wrappers = [c for c in li if c.tag == "p" and c.find("disp-formula") is not None]
    assert len(p_wrappers) == 1


def test_multiple_disp_formulas_each_wrapped(xml_file):
    xml = MINIMAL_DOC.format(
        list_item="""\
<list-item id="i1">
  <p id="i1.p1">Text.</p>
  <disp-formula id="EQ1"/>
  <disp-formula id="EQ2"/>
</list-item>"""
    )
    path = xml_file(xml)
    fix_disp_formula_in_list_item(path)

    root = ET.parse(path).getroot()
    li = root.find(".//list-item")
    assert li.find("disp-formula") is None
    p_wrappers = [c for c in li if c.tag == "p" and c.find("disp-formula") is not None]
    assert len(p_wrappers) == 2


def test_disp_formula_already_in_p_unchanged(xml_file):
    xml = MINIMAL_DOC.format(
        list_item="""\
<list-item id="i1">
  <p id="i1.p1">Text <disp-formula id="EQ1"/>.</p>
</list-item>"""
    )
    path = xml_file(xml)
    fix_disp_formula_in_list_item(path)

    root = ET.parse(path).getroot()
    li = root.find(".//list-item")
    # The disp-formula is inside the existing <p>, which is unchanged
    p = li.find("p")
    assert p is not None
    assert p.find("disp-formula") is not None


def test_no_disp_formula_unchanged(xml_file):
    xml = MINIMAL_DOC.format(
        list_item="""\
<list-item id="i1">
  <p id="i1.p1">Just text.</p>
</list-item>"""
    )
    path = xml_file(xml)
    fix_disp_formula_in_list_item(path)

    root = ET.parse(path).getroot()
    li = root.find(".//list-item")
    children = list(li)
    assert len(children) == 1
    assert children[0].tag == "p"
