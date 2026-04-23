"""Unit tests for fix_metadata: journal-meta and article-meta injection."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from latex_jats.convert import fix_metadata


def _write_xml(tmp_path, content):
    p = tmp_path / "article.xml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _write_tex(tmp_path, content):
    p = tmp_path / "main.tex"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_journal_meta(tmp_path):
    """fix_metadata replaces journal-meta with the constant CCR block."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta>
      <journal-id>not-yet-known</journal-id>
      <issn>not-yet-known</issn>
    </journal-meta>
    <article-meta>
      <article-id>not-yet-known</article-id>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(tmp_path, r"\begin{document}")

    fix_metadata(xml_file, tex_file)

    root = ET.parse(xml_file).getroot()
    jm = root.find(".//journal-meta")
    assert jm is not None

    jid = jm.find("journal-id")
    assert jid is not None
    assert jid.get("journal-id-type") == "publisher-id"
    assert jid.text == "CCR"

    jtg = jm.find("journal-title-group")
    assert jtg is not None
    assert jtg.findtext("journal-title") == "Computational Communication Research"

    issns = {e.get("pub-type"): e.text for e in jm.findall("issn")}
    assert issns.get("ppub") is None
    assert issns.get("epub") == "2665-9085"

    pub = jm.find("publisher")
    assert pub is not None
    assert pub.findtext("publisher-name") == "Amsterdam University Press"
    assert pub.findtext("publisher-loc") == "Amsterdam"


def test_article_meta(tmp_path):
    """fix_metadata injects doi, publisher-id, volume, issue, fpage, pub-date."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta>
      <journal-id>not-yet-known</journal-id>
      <issn>not-yet-known</issn>
    </journal-meta>
    <article-meta>
      <article-id>not-yet-known</article-id>
      <title-group>
        <article-title>Test</article-title>
      </title-group>
      <contrib-group/>
      <abstract>
        <p>Some abstract text.</p>
      </abstract>
      <kwd-group>
        <kwd>test</kwd>
      </kwd-group>
      <permissions>
        <copyright-statement>unknown</copyright-statement>
      </permissions>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(
        tmp_path,
        r"""\
\volume{5}
\pubnumber{1}
\pubyear{2023}
\firstpage{85}
\doi{10.5117/CCR2023.1.004.KATH}
\begin{document}
""",
    )

    fix_metadata(xml_file, tex_file)

    root = ET.parse(xml_file).getroot()
    am = root.find(".//article-meta")
    assert am is not None

    # Two article-id elements: doi and publisher-id
    article_ids = {e.get("pub-id-type"): e.text for e in am.findall("article-id")}
    assert article_ids.get("doi") == "10.5117/CCR2023.1.004.KATH"
    assert article_ids.get("publisher-id") == "CCR2023.1.004.KATH"

    # pub-date / year
    pub_date = am.find("pub-date")
    assert pub_date is not None
    assert pub_date.get("pub-type") == "epub"
    assert pub_date.findtext("year") == "2023"

    assert am.findtext("volume") == "5"
    assert am.findtext("issue") == "1"
    assert am.findtext("fpage") == "85"

    # article-categories with subject "Article"
    art_cat = am.find("article-categories")
    assert art_cat is not None
    assert art_cat.findtext("subj-group/subject") == "Article"

    # permissions: full copyright + license block
    perm = am.find("permissions")
    assert perm is not None
    assert perm.findtext("copyright-year") == "2023"
    assert perm.findtext("copyright-holder") == "The authors"
    assert perm.find("license") is not None
    assert perm.find("license").get("license-type") == "open-access"

    # abstract gets <title>Abstract</title>
    abstract = root.find(".//abstract")
    assert abstract is not None
    assert abstract.findtext("title") == "Abstract"

    # kwd-group gets <title>Keywords:</title>
    kwd_group = root.find(".//kwd-group")
    assert kwd_group is not None
    assert kwd_group.findtext("title") == "Keywords:"

    # New elements should appear before <permissions>
    children = list(am)
    perm_idx = next(i for i, e in enumerate(children) if e.tag == "permissions")
    fpage_idx = next(i for i, e in enumerate(children) if e.tag == "fpage")
    assert fpage_idx < perm_idx


def test_history_and_expanded_pub_date(tmp_path):
    """fix_metadata emits <history><date date-type="..."/></history> and expands
    <pub-date> to <day><month><year> when date_published is present."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta><journal-id>x</journal-id><issn>x</issn></journal-meta>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
      <contrib-group/>
      <permissions><copyright-statement>x</copyright-statement></permissions>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(
        tmp_path,
        r"""\
\volume{6}
\pubnumber{1}
\pubyear{2026}
\firstpage{1}
\doi{10.5117/CCR2026.1.2.SMOKE}
\datereceived{2025-05-28}
\dateaccepted{2026-01-14}
\datepublished{2026-02-16}
\begin{document}
""",
    )

    fix_metadata(xml_file, tex_file)

    root = ET.parse(xml_file).getroot()
    am = root.find(".//article-meta")

    # <pub-date> expanded to day/month/year
    pub_date = am.find("pub-date")
    assert pub_date.findtext("day") == "16"
    assert pub_date.findtext("month") == "2"
    assert pub_date.findtext("year") == "2026"

    # <history> with received + accepted dates
    hist = am.find("history")
    assert hist is not None
    dates = hist.findall("date")
    by_type = {d.get("date-type"): d for d in dates}
    assert set(by_type) == {"received", "accepted"}
    assert by_type["received"].findtext("day") == "28"
    assert by_type["received"].findtext("month") == "5"
    assert by_type["received"].findtext("year") == "2025"
    assert by_type["received"].get("iso-8601-date") == "2025-05-28"
    assert by_type["accepted"].findtext("day") == "14"
    assert by_type["accepted"].findtext("month") == "1"
    assert by_type["accepted"].findtext("year") == "2026"
    assert by_type["accepted"].get("iso-8601-date") == "2026-01-14"

    # <pub-date> does NOT carry iso-8601-date — the guide's spec for pub-date
    # only shows the child-elements form, so we keep it minimal there.
    pub_date = am.find("pub-date")
    assert pub_date.get("iso-8601-date") is None

    # <history> must sit before <permissions>
    children = list(am)
    hist_idx = children.index(hist)
    perm_idx = next(i for i, e in enumerate(children) if e.tag == "permissions")
    assert hist_idx < perm_idx


def test_history_not_emitted_when_no_dates(tmp_path):
    """Without date_received/date_accepted the <history> block is not added."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta><journal-id>x</journal-id><issn>x</issn></journal-meta>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(tmp_path, r"\pubyear{2024}" + "\n" + r"\begin{document}")
    fix_metadata(xml_file, tex_file)
    root = ET.parse(xml_file).getroot()
    assert root.find(".//article-meta/history") is None


def test_existing_empty_history_replaced(tmp_path):
    """Quarto-emitted empty <history/> is replaced by the re-emitted block."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta><journal-id>x</journal-id><issn>x</issn></journal-meta>
    <article-meta>
      <title-group><article-title>T</article-title></title-group>
      <history/>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(
        tmp_path,
        r"""\
\datereceived{2025-05-28}
\dateaccepted{2026-01-14}
\begin{document}
""",
    )
    fix_metadata(xml_file, tex_file)
    root = ET.parse(xml_file).getroot()
    am = root.find(".//article-meta")
    histories = am.findall("history")
    assert len(histories) == 1
    assert len(histories[0]) == 2  # one <date> per type


def test_pub_date_year_only_fallback(tmp_path):
    """When only \\pubyear is set (no \\datepublished), emit <pub-date><year/>."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta><journal-id>x</journal-id><issn>x</issn></journal-meta>
    <article-meta/>
  </front>
</article>""",
    )
    tex_file = _write_tex(tmp_path, r"\pubyear{2024}" + "\n" + r"\begin{document}")
    fix_metadata(xml_file, tex_file)
    pub_date = ET.parse(xml_file).getroot().find(".//pub-date")
    assert pub_date is not None
    assert pub_date.findtext("year") == "2024"
    assert pub_date.find("day") is None
    assert pub_date.find("month") is None


def test_kwd_whitespace_trimmed(tmp_path):
    """fix_metadata strips leading/trailing whitespace from <kwd> text (LaTeXML
    comma-tokenisation leaves a leading space on all but the first keyword)."""
    xml_file = _write_xml(
        tmp_path,
        """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <journal-meta><journal-id>x</journal-id><issn>x</issn></journal-meta>
    <article-meta>
      <kwd-group>
        <kwd>first keyword</kwd>
        <kwd> second keyword</kwd>
        <kwd>  third keyword  </kwd>
      </kwd-group>
    </article-meta>
  </front>
</article>""",
    )
    tex_file = _write_tex(tmp_path, r"\begin{document}")

    fix_metadata(xml_file, tex_file)

    root = ET.parse(xml_file).getroot()
    kwds = [kwd.text for kwd in root.findall(".//kwd")]
    assert kwds == ["first keyword", "second keyword", "third keyword"]
