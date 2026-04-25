import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import fix_supplementary_material

XLINK = "http://www.w3.org/1999/xlink"
NS = {"xlink": XLINK}

DOC_TEMPLATE = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
      <abstract><p>abs</p></abstract>
      <kwd-group><kwd>k</kwd></kwd-group>
    </article-meta>
  </front>
  <body>{body}</body>
  <back>{back}</back>
</article>"""


def _parse(path):
    return ET.parse(path).getroot()


def test_single_marker_in_body(xml_file):
    body = (
        '<sec><p>before '
        '<styled-content style-type="ccr-suppmat">See: '
        '<ext-link xlink:href="https://example.org/a" ext-link-type="uri">https://example.org/a</ext-link>'
        '</styled-content> after</p></sec>'
    )
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    fix_supplementary_material(path)

    root = _parse(path)
    sm = root.findall(".//article-meta/supplementary-material")
    assert len(sm) == 1
    assert sm[0].get("id") == "suppmat1"
    assert sm[0].get(f"{{{XLINK}}}href") == "https://example.org/a"
    caption = sm[0].find("caption/p")
    assert caption.text == "See: "
    assert caption.find("ext-link").get(f"{{{XLINK}}}href") == "https://example.org/a"

    # Marker unwrapped, inline text preserved
    assert root.find(".//body//styled-content") is None
    p = root.find(".//body//p")
    assert p.text == "before See: "
    assert p.find("ext-link") is not None
    assert p.find("ext-link").tail == " after"


def test_multiple_markers_document_order(xml_file):
    body = (
        '<p><styled-content style-type="ccr-suppmat">First '
        '<ext-link xlink:href="https://ex.org/1">https://ex.org/1</ext-link>'
        '</styled-content></p>'
        '<p><styled-content style-type="ccr-suppmat">Second '
        '<ext-link xlink:href="https://ex.org/2">https://ex.org/2</ext-link>'
        '</styled-content></p>'
    )
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    fix_supplementary_material(path)

    root = _parse(path)
    sm = root.findall(".//article-meta/supplementary-material")
    assert [e.get("id") for e in sm] == ["suppmat1", "suppmat2"]
    assert sm[0].get(f"{{{XLINK}}}href") == "https://ex.org/1"
    assert sm[1].get(f"{{{XLINK}}}href") == "https://ex.org/2"


def test_marker_inside_footnote_in_back(xml_file):
    """fix_footnotes runs earlier and moves <fn> into <back>/<fn-group>."""
    back = (
        '<fn-group><fn id="id1"><p>'
        '<styled-content style-type="ccr-suppmat">Footnote suppmat: '
        '<ext-link xlink:href="https://osf.io/x">https://osf.io/x</ext-link>'
        '</styled-content></p></fn></fn-group>'
    )
    path = xml_file(DOC_TEMPLATE.format(body="<sec><p>x</p></sec>", back=back))
    fix_supplementary_material(path)

    root = _parse(path)
    sm = root.find(".//article-meta/supplementary-material")
    assert sm is not None
    assert sm.get(f"{{{XLINK}}}href") == "https://osf.io/x"

    # Footnote retains its content with marker unwrapped
    fn_p = root.find(".//back//fn/p")
    assert fn_p.find("styled-content") is None
    assert fn_p.text == "Footnote suppmat: "
    assert fn_p.find("ext-link") is not None


def test_marker_with_multiple_ext_links_warns(xml_file, caplog):
    """Multiple URLs inside one marker: first becomes xlink:href, warning lists the rest."""
    body = (
        '<p><styled-content style-type="ccr-suppmat">See: '
        '<ext-link xlink:href="https://ex.org/primary">primary</ext-link>'
        ' and also '
        '<ext-link xlink:href="https://ex.org/secondary">secondary</ext-link>'
        '</styled-content></p>'
    )
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    with caplog.at_level(logging.WARNING, logger="jatsmith.convert"):
        fix_supplementary_material(path)

    root = _parse(path)
    sm = root.find(".//article-meta/supplementary-material")
    assert sm.get(f"{{{XLINK}}}href") == "https://ex.org/primary"
    # Both links remain visible in the caption
    caption_links = sm.findall(".//caption//ext-link")
    assert len(caption_links) == 2

    msgs = [r.message for r in caplog.records]
    assert any("contains 2 URLs" in m for m in msgs)
    assert any("https://ex.org/secondary" in m for m in msgs)


def test_marker_without_ext_link_warns(xml_file, caplog):
    body = (
        '<p><styled-content style-type="ccr-suppmat">Plain text only'
        '</styled-content></p>'
    )
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    with caplog.at_level(logging.WARNING, logger="jatsmith.convert"):
        fix_supplementary_material(path)

    root = _parse(path)
    sm = root.find(".//article-meta/supplementary-material")
    assert sm is not None
    assert sm.get(f"{{{XLINK}}}href") is None
    assert sm.find("caption/p").text == "Plain text only"
    assert any("has no <ext-link>" in r.message for r in caplog.records)


def test_supplementary_material_inserted_before_permissions(xml_file):
    """<supplementary-material> must be placed before <permissions> per JATS schema."""
    doc = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
      <fpage>1</fpage>
      <permissions><copyright-statement>c</copyright-statement></permissions>
      <abstract><p>abs</p></abstract>
      <kwd-group><kwd>k</kwd></kwd-group>
    </article-meta>
  </front>
  <body><p><styled-content style-type="ccr-suppmat">X <ext-link xlink:href="https://e.org">e</ext-link></styled-content></p></body>
</article>"""
    path = xml_file(doc)
    fix_supplementary_material(path)

    root = _parse(path)
    am = root.find(".//article-meta")
    tags = [e.tag for e in am]
    # supplementary-material appears before permissions
    assert tags.index("supplementary-material") < tags.index("permissions")


def test_supplementary_material_inserted_before_history(xml_file):
    """<supplementary-material> must come before <history> per JATS 1.2."""
    doc = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
      <fpage>1</fpage>
      <history><date date-type="received"><year>2025</year></date></history>
      <permissions><copyright-statement>c</copyright-statement></permissions>
    </article-meta>
  </front>
  <body><p><styled-content style-type="ccr-suppmat">X <ext-link xlink:href="https://e.org">e</ext-link></styled-content></p></body>
</article>"""
    path = xml_file(doc)
    fix_supplementary_material(path)

    root = _parse(path)
    am = root.find(".//article-meta")
    tags = [e.tag for e in am]
    assert tags.index("supplementary-material") < tags.index("history")


def test_no_markers_no_change(xml_file):
    """Absence of markers leaves the file untouched."""
    body = '<sec><p>plain content</p></sec>'
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    fix_supplementary_material(path)

    root = _parse(path)
    assert root.find(".//article-meta/supplementary-material") is None


def test_named_content_marker_from_quarto(xml_file):
    """Pandoc/Quarto emits <named-content content-type="ccr-suppmat"> for
    [...]{.ccr-suppmat} spans; it must be handled the same as the LaTeX
    pipeline's <styled-content style-type="ccr-suppmat"> marker."""
    back = (
        '<fn-group><fn id="fn1"><p>'
        '<named-content content-type="ccr-suppmat">See: '
        '<ext-link xlink:href="https://osf.io/q">https://osf.io/q</ext-link>'
        '</named-content></p></fn></fn-group>'
    )
    path = xml_file(DOC_TEMPLATE.format(body="<sec><p>x</p></sec>", back=back))
    fix_supplementary_material(path)

    root = _parse(path)
    sm = root.find(".//article-meta/supplementary-material")
    assert sm is not None
    assert sm.get("id") == "suppmat1"
    assert sm.get(f"{{{XLINK}}}href") == "https://osf.io/q"

    # Marker unwrapped, link still in the footnote
    fn_p = root.find(".//back//fn/p")
    assert fn_p.find("named-content") is None
    assert fn_p.find("ext-link") is not None


def test_unwrap_preserves_tail_and_sibling_text(xml_file):
    """Marker tail text and surrounding siblings survive the unwrap."""
    body = (
        '<p>pre <b>bold</b> mid '
        '<styled-content style-type="ccr-suppmat">X '
        '<ext-link xlink:href="https://e.org">https://e.org</ext-link> Y'
        '</styled-content> tail <i>it</i> end</p>'
    )
    path = xml_file(DOC_TEMPLATE.format(body=body, back=""))
    fix_supplementary_material(path)

    root = _parse(path)
    p = root.find(".//body//p")
    # serialize and check readable-text content is contiguous
    text = ET.tostring(p, encoding="unicode")
    assert "pre " in text
    assert "mid X " in text
    assert "Y tail " in text
    assert "end" in text
    # marker gone, ext-link survives once in body (plus once in caption)
    assert p.find("styled-content") is None
    assert p.find("ext-link") is not None
