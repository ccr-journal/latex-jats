"""Unit tests for the Quarto post-processing fixups."""
import xml.etree.ElementTree as ET

from latex_jats.quarto import (
    add_fig_table_labels,
    clean_element_citations,
    drop_empty_refs_section,
    fix_corresp_xref,
    fix_empty_history,
    inject_metadata_from_yaml,
    move_appendix_to_back,
    move_fn_group_to_back,
    parse_qmd_frontmatter,
    unwrap_table_fig,
)


def _parse(path):
    return ET.parse(path).getroot()


def test_fix_empty_history(xml_file):
    p = xml_file('<article><front><article-meta><history/></article-meta></front></article>')
    fix_empty_history(p)
    root = _parse(p)
    assert root.find(".//history") is None


def test_fix_empty_history_keeps_populated(xml_file):
    p = xml_file('<article><front><article-meta><history><date date-type="received"><year>2024</year></date></history></article-meta></front></article>')
    fix_empty_history(p)
    root = _parse(p)
    assert root.find(".//history") is not None


def test_fix_corresp_xref(xml_file):
    p = xml_file(
        '<article><front><article-meta><contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<string-name>Jane Doe<xref ref-type="fn" rid="fn1">1</xref></string-name>'
        '</contrib></contrib-group></article-meta></front></article>'
    )
    fix_corresp_xref(p)
    root = _parse(p)
    string_name = root.find(".//string-name")
    assert string_name.find("xref") is None
    contrib = root.find(".//contrib")
    assert contrib.find("xref") is not None
    assert contrib.find("xref").get("rid") == "fn1"


def test_unwrap_table_fig(xml_file):
    p = xml_file(
        '<article><body>'
        '<fig id="tbl-1"><caption><p>Table 1: Data</p></caption>'
        '<table-wrap><table><tr><td>cell</td></tr></table></table-wrap>'
        '</fig></body></article>'
    )
    unwrap_table_fig(p)
    root = _parse(p)
    assert root.find(".//body/fig") is None
    tw = root.find(".//body/table-wrap")
    assert tw is not None
    assert tw.get("id") == "tbl-1"


def test_unwrap_table_fig_warns_on_empty(xml_file, caplog):
    import logging
    p = xml_file(
        '<article><body>'
        '<fig id="tbl-2"><caption><p>Table 2: Empty</p></caption></fig>'
        '</body></article>'
    )
    with caplog.at_level(logging.WARNING):
        unwrap_table_fig(p)
    assert any("tbl-2" in r.message for r in caplog.records)


def test_add_fig_table_labels(xml_file):
    p = xml_file(
        '<article><body>'
        '<fig id="fig-1"><caption><p>Figure 1: A nice plot</p></caption></fig>'
        '<table-wrap id="tbl-1"><caption><p>Table A2: Results</p></caption></table-wrap>'
        '</body></article>'
    )
    add_fig_table_labels(p)
    root = _parse(p)
    fig = root.find(".//fig")
    assert fig.find("label").text == "Figure 1:"
    assert fig.find("caption/p").text == "A nice plot"
    tw = root.find(".//table-wrap")
    assert tw.find("label").text == "Table A2:"
    assert tw.find("caption/p").text == "Results"


def test_move_fn_group_to_back(xml_file):
    p = xml_file(
        '<article><body><p>Body text</p>'
        '<fn-group><fn id="fn1"><p>note</p></fn></fn-group>'
        '</body><back/></article>'
    )
    move_fn_group_to_back(p)
    root = _parse(p)
    assert root.find(".//body/fn-group") is None
    assert root.find(".//back/fn-group") is not None


def test_move_fn_group_creates_back(xml_file):
    p = xml_file(
        '<article><body><p>Body text</p>'
        '<fn-group><fn id="fn1"><p>note</p></fn></fn-group>'
        '</body></article>'
    )
    move_fn_group_to_back(p)
    root = _parse(p)
    assert root.find("back") is not None
    assert root.find(".//back/fn-group") is not None


def test_drop_empty_refs_section(xml_file):
    p = xml_file(
        '<article><body><sec id="references"><title>References</title><p/></sec></body>'
        '<back><ref-list><ref id="r1"/></ref-list></back></article>'
    )
    drop_empty_refs_section(p)
    root = _parse(p)
    assert root.find(".//body/sec[@id='references']") is None
    assert root.find(".//back/ref-list") is not None


def test_drop_empty_refs_section_keeps_nonempty(xml_file):
    p = xml_file(
        '<article><body><sec id="references"><title>References</title><p>Stuff</p></sec></body>'
        '<back><ref-list><ref id="r1"/></ref-list></back></article>'
    )
    drop_empty_refs_section(p)
    root = _parse(p)
    assert root.find(".//body/sec[@id='references']") is not None


def test_clean_element_citations(xml_file):
    p = xml_file(
        '<article><back><ref-list><ref id="r1"><element-citation>'
        '<article-title>Foo</article-title>'
        '<date-in-citation content-type="access-date"><year>2026</year></date-in-citation>'
        '</element-citation></ref></ref-list></back></article>'
    )
    clean_element_citations(p)
    root = _parse(p)
    assert root.find(".//date-in-citation") is None
    assert root.find(".//article-title").text == "Foo"


def test_move_appendix_to_back(xml_file):
    p = xml_file(
        '<article><body><sec id="appendix"><title>Appendix</title><p>App text</p></sec></body>'
        '<back/></article>'
    )
    move_appendix_to_back(p)
    root = _parse(p)
    assert root.find(".//body/sec[@id='appendix']") is None
    app = root.find(".//back/app-group/app")
    assert app is not None
    assert app.get("id") == "appendix"


def test_parse_qmd_frontmatter(tmp_path):
    qmd = tmp_path / "test.qmd"
    qmd.write_text(
        '---\n'
        'title: "My Title"\n'
        'doi: 10.5117/CCR2026.1.1.TEST\n'
        'volume: 8\n'
        'pubnumber: 2\n'
        'pubyear: 2026\n'
        'firstpage: 1\n'
        '---\n\n'
        'Body text\n',
        encoding='utf-8',
    )
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/CCR2026.1.1.TEST"
    assert str(meta["volume"]) == "8"
    assert str(meta["pubnumber"]) == "2"
    assert meta["title"] == "My Title"


def test_inject_metadata_from_yaml(tmp_path, xml_file):
    qmd = tmp_path / "x.qmd"
    qmd.write_text(
        '---\n'
        'doi: 10.5117/CCR2026.2.11.URMA\n'
        'volume: 8\n'
        'pubnumber: 2\n'
        'pubyear: 2026\n'
        'firstpage: 1\n'
        'lastpage: 30\n'
        '---\n\nBody\n',
        encoding='utf-8',
    )
    p = xml_file(
        '<article><front><article-meta>'
        '<title-group><article-title>T</article-title></title-group>'
        '<abstract><p>abs</p></abstract>'
        '</article-meta></front></article>'
    )
    inject_metadata_from_yaml(p, str(qmd))
    root = _parse(p)
    jm = root.find(".//journal-meta")
    assert jm is not None
    assert jm.find("journal-id").text == "CCR"
    am = root.find(".//article-meta")
    doi = am.find("article-id[@pub-id-type='doi']")
    assert doi is not None and doi.text == "10.5117/CCR2026.2.11.URMA"
    pubid = am.find("article-id[@pub-id-type='publisher-id']")
    assert pubid is not None and pubid.text == "CCR2026.2.11.URMA"
    assert am.find("volume").text == "8"
    assert am.find("issue").text == "2"
    assert am.find("fpage").text == "1"
    assert am.find("lpage").text == "30"
    assert am.find("pub-date/year").text == "2026"
    assert am.find("permissions") is not None
    # abstract should now have a title
    assert root.find(".//abstract/title").text == "Abstract"
