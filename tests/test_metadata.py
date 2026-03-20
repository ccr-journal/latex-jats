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
    assert issns.get("print") == "2665-9085"
    assert issns.get("electronic") == "2665-9085"

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
    assert pub_date.get("pub-type") == "electronic"
    assert pub_date.findtext("year") == "2023"

    assert am.findtext("volume") == "5"
    assert am.findtext("issue") == "1"
    assert am.findtext("fpage") == "85"

    # New elements should appear before <permissions>
    children = list(am)
    perm_idx = next(i for i, e in enumerate(children) if e.tag == "permissions")
    fpage_idx = next(i for i, e in enumerate(children) if e.tag == "fpage")
    assert fpage_idx < perm_idx
