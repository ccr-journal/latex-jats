"""Unit tests for the Quarto post-processing fixups."""
import xml.etree.ElementTree as ET

from latex_jats.quarto import (
    add_fig_table_labels,
    drop_empty_refs_section,
    fix_corresp_xref,
    fix_empty_history,
    inject_metadata_from_yaml,
    inline_affiliations,
    move_appendix_to_back,
    move_fn_group_to_back,
    parse_qmd_frontmatter,
    rebuild_element_citations,
    reorder_back_matter,
    set_ref_list_title,
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


def test_inline_affiliations_basic(xml_file):
    p = xml_file(
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref></contrib>'
        '</contrib-group>'
        '<aff id="aff-1"><institution-wrap><institution>Uni A</institution></institution-wrap></aff>'
        '</article-meta></front></article>'
    )
    inline_affiliations(p)
    root = _parse(p)
    article_meta = root.find(".//article-meta")
    assert article_meta.find("aff") is None
    contrib = root.find(".//contrib")
    assert contrib.find("xref") is None
    aff = contrib.find("aff")
    assert aff is not None
    assert aff.get("id") is None
    assert aff.find("institution-wrap/institution").text == "Uni A"


def test_inline_affiliations_shared(xml_file):
    p = xml_file(
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref></contrib>'
        '<contrib contrib-type="author"><name><surname>Roe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref></contrib>'
        '</contrib-group>'
        '<aff id="aff-1"><institution-wrap><institution>Uni A</institution></institution-wrap></aff>'
        '</article-meta></front></article>'
    )
    inline_affiliations(p)
    root = _parse(p)
    assert root.find(".//article-meta/aff") is None
    contribs = root.findall(".//contrib")
    assert len(contribs) == 2
    for c in contribs:
        assert c.find("xref") is None
        assert c.find("aff/institution-wrap/institution").text == "Uni A"


def test_inline_affiliations_multiple_per_author(xml_file):
    p = xml_file(
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref>'
        '<xref ref-type="aff" rid="aff-2">b</xref></contrib>'
        '</contrib-group>'
        '<aff id="aff-1"><institution-wrap><institution>Uni A</institution></institution-wrap></aff>'
        '<aff id="aff-2"><institution-wrap><institution>Uni B</institution></institution-wrap></aff>'
        '</article-meta></front></article>'
    )
    inline_affiliations(p)
    root = _parse(p)
    assert root.find(".//article-meta/aff") is None
    affs = root.findall(".//contrib/aff")
    assert len(affs) == 2
    assert affs[0].find("institution-wrap/institution").text == "Uni A"
    assert affs[1].find("institution-wrap/institution").text == "Uni B"


def test_inline_affiliations_preserves_fn_xref(xml_file):
    p = xml_file(
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref>'
        '<xref ref-type="fn" rid="fn1">1</xref></contrib>'
        '</contrib-group>'
        '<aff id="aff-1"><institution-wrap><institution>Uni A</institution></institution-wrap></aff>'
        '</article-meta></front></article>'
    )
    inline_affiliations(p)
    root = _parse(p)
    contrib = root.find(".//contrib")
    fn_xrefs = [x for x in contrib.findall("xref") if x.get("ref-type") == "fn"]
    assert len(fn_xrefs) == 1
    assert fn_xrefs[0].get("rid") == "fn1"
    assert contrib.find("aff") is not None


def test_inline_affiliations_orphan_warns(xml_file, caplog):
    import logging
    p = xml_file(
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<xref ref-type="aff" rid="aff-1">a</xref></contrib>'
        '</contrib-group>'
        '<aff id="aff-1"><institution-wrap><institution>Uni A</institution></institution-wrap></aff>'
        '<aff id="aff-2"><institution-wrap><institution>Uni B</institution></institution-wrap></aff>'
        '</article-meta></front></article>'
    )
    with caplog.at_level(logging.WARNING):
        inline_affiliations(p)
    root = _parse(p)
    remaining = root.findall(".//article-meta/aff")
    assert len(remaining) == 1
    assert remaining[0].get("id") == "aff-2"
    assert any("aff-2" in r.message for r in caplog.records)


def test_inline_affiliations_noop_when_already_nested(xml_file):
    original = (
        '<article><front><article-meta>'
        '<contrib-group>'
        '<contrib contrib-type="author"><name><surname>Doe</surname></name>'
        '<aff>Uni A</aff></contrib>'
        '</contrib-group>'
        '</article-meta></front></article>'
    )
    p = xml_file(original)
    inline_affiliations(p)
    with open(p, encoding="utf-8") as f:
        assert f.read() == original


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


_XLINK = "{http://www.w3.org/1999/xlink}"


def test_rebuild_element_citations_journal(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="ref-smith2024">'
        '<element-citation publication-type="article-journal">'
        '<person-group person-group-type="author">'
        '<name><surname>Smith</surname><given-names>Jane A.</given-names></name>'
        '<name><surname>Doe</surname><given-names>John</given-names></name>'
        '</person-group>'
        '<article-title>A Study of Things</article-title>'
        '<source>Journal of Things</source>'
        '<year iso-8601-date="2024-03">2024</year>'
        '<month>03</month>'
        '<volume>12</volume>'
        '<issue>3</issue>'
        '<issn>1234-5678</issn>'
        '<uri>https://example.com/x</uri>'
        '<pub-id pub-id-type="doi">10.1234/abc.2024.003</pub-id>'
        '<fpage>45</fpage>'
        '<lpage>67</lpage>'
        '</element-citation>'
        '</ref>'
        '</ref-list></back></article>'
    )
    rebuild_element_citations(p)
    root = _parse(p)
    ref = root.find(".//ref")
    assert ref.find("element-citation") is None
    mc = ref.find("mixed-citation")
    assert mc is not None
    assert mc.get("publication-type") == "journal"
    surnames = [sn.text for sn in mc.findall("string-name/surname")]
    assert surnames == ["Smith", "Doe"]
    assert mc.find("article-title").text == "A Study of Things"
    assert mc.find("source/italic").text == "Journal of Things"
    assert mc.find("year").text == "2024"
    assert mc.find("volume").text == "12"
    assert mc.find("issue").text == "3"
    assert mc.find("fpage").text == "45"
    assert mc.find("lpage").text == "67"
    link = mc.find("ext-link")
    assert link is not None
    assert link.get("ext-link-type") == "doi"
    assert link.get(f"{_XLINK}href") == "https://doi.org/10.1234/abc.2024.003"
    assert link.text == "https://doi.org/10.1234/abc.2024.003"
    # Given names should be collapsed to APA initials for consistency with
    # the biblatex-driven LaTeX pipeline.
    given = [g.text for g in mc.findall("string-name/given-names")]
    assert given == ["J. A.", "J."]
    # Sanity-check APA separators are inline (the original bug was that
    # Quarto's element-citation emitted fields with no punctuation, so the
    # rendered text was run-on).
    flat = "".join(mc.itertext())
    assert "Smith, J. A." in flat
    assert ", & Doe, J." in flat
    assert " (2024). " in flat
    assert ". Journal of Things, " in flat
    assert "12(3), 45\u201367. https://doi.org/" in flat


def test_rebuild_element_citations_chapter(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="ref-cuddy2008">'
        '<element-citation publication-type="chapter">'
        '<person-group person-group-type="author">'
        '<name><surname>Cuddy</surname><given-names>Amy J. C.</given-names></name>'
        '</person-group>'
        '<article-title>Warmth and Competence</article-title>'
        '<source>Advances in Experimental Social Psychology</source>'
        '<publisher-name>Elsevier</publisher-name>'
        '<year iso-8601-date="2008">2008</year>'
        '<volume>40</volume>'
        '<fpage>61</fpage>'
        '<lpage>149</lpage>'
        '</element-citation>'
        '</ref>'
        '</ref-list></back></article>'
    )
    rebuild_element_citations(p)
    root = _parse(p)
    mc = root.find(".//mixed-citation")
    assert mc.get("publication-type") == "book"
    assert mc.find("chapter-title").text == "Warmth and Competence"
    assert mc.find("source/italic").text == "Advances in Experimental Social Psychology"
    assert mc.find("fpage").text == "61"
    assert mc.find("lpage").text == "149"
    assert mc.find("publisher-name").text == "Elsevier"
    flat = "".join(mc.itertext())
    assert "In " in flat
    assert "(pp. 61" in flat


def test_rebuild_element_citations_book(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="ref-butler2011">'
        '<element-citation publication-type="book">'
        '<person-group person-group-type="author">'
        '<name><surname>Butler</surname><given-names>Judith</given-names></name>'
        '</person-group>'
        '<source>Gender Trouble</source>'
        '<publisher-name>Routledge</publisher-name>'
        '<year iso-8601-date="2011">2011</year>'
        '<pub-id pub-id-type="doi">10.4324/9780203824979</pub-id>'
        '</element-citation>'
        '</ref>'
        '</ref-list></back></article>'
    )
    rebuild_element_citations(p)
    root = _parse(p)
    mc = root.find(".//mixed-citation")
    assert mc.get("publication-type") == "book"
    assert mc.find("source/italic").text == "Gender Trouble"
    assert mc.find("publisher-name").text == "Routledge"
    assert mc.find("article-title") is None
    assert mc.find("chapter-title") is None
    link = mc.find("ext-link")
    assert link.get("ext-link-type") == "doi"
    assert link.get(f"{_XLINK}href") == "https://doi.org/10.4324/9780203824979"


def test_rebuild_element_citations_uri_only(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="ref-web">'
        '<element-citation publication-type="webpage">'
        '<person-group person-group-type="author">'
        '<name><surname>Roe</surname><given-names>R.</given-names></name>'
        '</person-group>'
        '<source>A Blog Post</source>'
        '<year iso-8601-date="2022">2022</year>'
        '<uri>https://example.com/post</uri>'
        '</element-citation>'
        '</ref>'
        '</ref-list></back></article>'
    )
    rebuild_element_citations(p)
    root = _parse(p)
    mc = root.find(".//mixed-citation")
    link = mc.find("ext-link")
    assert link is not None
    assert link.get("ext-link-type") == "uri"
    assert link.get(f"{_XLINK}href") == "https://example.com/post"


def test_rebuild_element_citations_elocator_page(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="ref-bai2025">'
        '<element-citation publication-type="article-journal">'
        '<person-group person-group-type="author">'
        '<name><surname>Bai</surname><given-names>X.</given-names></name>'
        '</person-group>'
        '<article-title>Explicitly unbiased LLMs</article-title>'
        '<source>PNAS</source>'
        '<year>2025</year>'
        '<volume>122</volume>'
        '<issue>8</issue>'
        '<fpage>e2416228122</fpage>'
        '<lpage />'
        '</element-citation>'
        '</ref>'
        '</ref-list></back></article>'
    )
    rebuild_element_citations(p)
    root = _parse(p)
    mc = root.find(".//mixed-citation")
    assert mc.find("fpage").text == "e2416228122"
    # Empty <lpage/> should not produce a redundant lpage element
    assert mc.find("lpage") is None


def test_set_ref_list_title_fills_empty(xml_file):
    p = xml_file(
        '<article><back><ref-list><title/>'
        '<ref id="r1"><mixed-citation>x</mixed-citation></ref>'
        '</ref-list></back></article>'
    )
    set_ref_list_title(p)
    root = _parse(p)
    assert root.find(".//ref-list/title").text == "References"


def test_set_ref_list_title_preserves_existing(xml_file):
    p = xml_file(
        '<article><back><ref-list><title>Literature</title>'
        '<ref id="r1"><mixed-citation>x</mixed-citation></ref>'
        '</ref-list></back></article>'
    )
    set_ref_list_title(p)
    root = _parse(p)
    assert root.find(".//ref-list/title").text == "Literature"


def test_set_ref_list_title_inserts_when_missing(xml_file):
    p = xml_file(
        '<article><back><ref-list>'
        '<ref id="r1"><mixed-citation>x</mixed-citation></ref>'
        '</ref-list></back></article>'
    )
    set_ref_list_title(p)
    root = _parse(p)
    ref_list = root.find(".//ref-list")
    assert ref_list[0].tag == "title"
    assert ref_list[0].text == "References"


def test_reorder_back_matter(xml_file):
    p = xml_file(
        '<article><back>'
        '<ref-list><title>References</title></ref-list>'
        '<fn-group><fn id="fn1"/></fn-group>'
        '<app-group><app id="a"/></app-group>'
        '</back></article>'
    )
    reorder_back_matter(p)
    root = _parse(p)
    tags = [c.tag for c in root.find("back")]
    assert tags == ["app-group", "fn-group", "ref-list"]


def test_reorder_back_matter_noop_when_sorted(xml_file):
    p = xml_file(
        '<article><back>'
        '<app-group><app id="a"/></app-group>'
        '<fn-group><fn id="fn1"/></fn-group>'
        '<ref-list><title>References</title></ref-list>'
        '</back></article>'
    )
    reorder_back_matter(p)
    root = _parse(p)
    tags = [c.tag for c in root.find("back")]
    assert tags == ["app-group", "fn-group", "ref-list"]


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
