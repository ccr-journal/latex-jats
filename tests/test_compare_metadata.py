"""Unit tests for compare_metadata: OJS vs JATS metadata comparison."""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from latex_jats.convert import compare_metadata


# ── Lightweight stand-ins for the DB models ──────────────────────────────────


@dataclass
class FakeManuscript:
    title: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[list] = None
    doi: Optional[str] = None
    volume: Optional[str] = None
    issue_number: Optional[str] = None
    year: Optional[int] = None
    date_received: Optional[str] = None
    date_accepted: Optional[str] = None
    date_published: Optional[str] = None
    ojs_submission_id: Optional[int] = 1


@dataclass
class FakeAuthor:
    name: Optional[str]
    order: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────────


_JATS_TEMPLATE = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <article-id pub-id-type="doi">{doi}</article-id>
      <title-group>
        <article-title>{title}</article-title>
      </title-group>
      <contrib-group>
{contribs}
      </contrib-group>
      <volume>{volume}</volume>
      <issue>{issue}</issue>
      <pub-date pub-type="epub"><year>{year}</year></pub-date>
      <abstract>
        <title>Abstract</title>
        <p>{abstract}</p>
      </abstract>
      <kwd-group>
        <title>Keywords:</title>
{kwds}
      </kwd-group>
    </article-meta>
  </front>
</article>"""


def _contrib(surname, given):
    return (
        f'        <contrib contrib-type="author">'
        f'<name><surname>{surname}</surname>'
        f'<given-names>{given}</given-names></name></contrib>'
    )


def _kwd(text):
    return f"        <kwd>{text}</kwd>"


def _write_jats(tmp_path, *, title="A Title", abstract="Some abstract text.",
                authors=None, keywords=None, doi="10.5117/CCR2025.1.2.YAO",
                volume="7", issue="1", year="2025"):
    if authors is None:
        authors = [("Yao", "Jielu"), ("Ridout", "Travis N.")]
    if keywords is None:
        keywords = ["masks", "COVID-19"]
    contribs = "\n".join(_contrib(s, g) for s, g in authors)
    kwds = "\n".join(_kwd(k) for k in keywords)
    xml = _JATS_TEMPLATE.format(
        doi=doi, title=title, abstract=abstract,
        contribs=contribs, kwds=kwds,
        volume=volume, issue=issue, year=year,
    )
    p = tmp_path / "article.xml"
    p.write_text(xml, encoding="utf-8")
    return str(p)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_all_matching(tmp_path):
    """No warnings when everything matches."""
    jats = _write_jats(tmp_path)
    ms = FakeManuscript(
        title="A Title",
        abstract="Some abstract text.",
        keywords=["masks", "COVID-19"],
        doi="10.5117/CCR2025.1.2.YAO",
        volume="7",
        issue_number="1",
        year=2025,
    )
    authors = [
        FakeAuthor(name="Jielu Yao", order=0),
        FakeAuthor(name="Travis N. Ridout", order=1),
    ]
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, authors, output_json=out)
    results = json.loads(out.read_text())
    assert all(r["status"] == "ok" for r in results)


def test_title_mismatch(tmp_path):
    jats = _write_jats(tmp_path, title="Updated Title From LaTeX")
    ms = FakeManuscript(title="Original OJS Title")
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    title_result = next(r for r in results if r["field"] == "title")
    assert title_result["status"] == "mismatch"


def test_title_html_stripped(tmp_path):
    """HTML in OJS title is stripped for comparison."""
    jats = _write_jats(tmp_path, title="A Title With Emphasis")
    ms = FakeManuscript(title="A Title With <em>Emphasis</em>")
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    title_result = next(r for r in results if r["field"] == "title")
    assert title_result["status"] == "ok"


def test_abstract_mismatch(tmp_path):
    jats = _write_jats(tmp_path, abstract="New abstract from LaTeX.")
    ms = FakeManuscript(abstract="<p>Old abstract from OJS.</p>")
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    abstract_result = next(r for r in results if r["field"] == "abstract")
    assert abstract_result["status"] == "mismatch"


def test_abstract_html_stripped(tmp_path):
    """HTML tags in OJS abstract are stripped before comparison."""
    jats = _write_jats(tmp_path, abstract="Some abstract text.")
    ms = FakeManuscript(abstract="<p>Some abstract text.</p>")
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    abstract_result = next(r for r in results if r["field"] == "abstract")
    assert abstract_result["status"] == "ok"


def test_keyword_mismatch(tmp_path):
    jats = _write_jats(tmp_path, keywords=["masks", "politics"])
    ms = FakeManuscript(keywords=["masks", "COVID-19"])
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    kw_result = next(r for r in results if r["field"] == "keywords")
    assert kw_result["status"] == "mismatch"


def test_keyword_case_insensitive(tmp_path):
    jats = _write_jats(tmp_path, keywords=["Masks", "covid-19"])
    ms = FakeManuscript(keywords=["masks", "COVID-19"])
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    kw_result = next(r for r in results if r["field"] == "keywords")
    assert kw_result["status"] == "ok"


def test_author_count_mismatch(tmp_path):
    jats = _write_jats(tmp_path, authors=[("Yao", "Jielu")])
    ms = FakeManuscript()
    authors = [
        FakeAuthor(name="Jielu Yao", order=0),
        FakeAuthor(name="Travis N. Ridout", order=1),
    ]
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, authors, output_json=out)
    results = json.loads(out.read_text())
    auth_result = next(r for r in results if r["field"] == "authors")
    assert auth_result["status"] == "mismatch"


def test_author_name_mismatch(tmp_path):
    jats = _write_jats(tmp_path, authors=[("Yao", "Jielu"), ("Smith", "John")])
    ms = FakeManuscript()
    authors = [
        FakeAuthor(name="Jielu Yao", order=0),
        FakeAuthor(name="Travis N. Ridout", order=1),
    ]
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, authors, output_json=out)
    results = json.loads(out.read_text())
    auth_result = next(r for r in results if r["field"] == "authors")
    assert auth_result["status"] == "mismatch"


def test_author_order_match(tmp_path):
    """Authors match when names are the same in order."""
    jats = _write_jats(tmp_path, authors=[("Yao", "Jielu"), ("Ridout", "Travis N.")])
    ms = FakeManuscript()
    authors = [
        FakeAuthor(name="Jielu Yao", order=0),
        FakeAuthor(name="Travis N. Ridout", order=1),
    ]
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, authors, output_json=out)
    results = json.loads(out.read_text())
    auth_result = next(r for r in results if r["field"] == "authors")
    assert auth_result["status"] == "ok"


def test_doi_mismatch(tmp_path):
    jats = _write_jats(tmp_path, doi="10.5117/CCR2025.1.2.YAO")
    ms = FakeManuscript(doi="10.5117/CCR2025.1.99.WRONG")
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    doi_result = next(r for r in results if r["field"] == "doi")
    assert doi_result["status"] == "mismatch"


def test_missing_ojs_fields_skipped(tmp_path):
    """Fields that are None in OJS are not compared."""
    jats = _write_jats(tmp_path)
    ms = FakeManuscript()  # all None
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    # Only keywords produces a result (empty set vs non-empty set check skips)
    assert all(r["status"] == "ok" or r["field"] == "keywords" for r in results)


def test_no_output_json(tmp_path):
    """compare_metadata works without output_json (just logs)."""
    jats = _write_jats(tmp_path, title="Different")
    ms = FakeManuscript(title="Original")
    # Should not raise
    compare_metadata(jats, ms, [])


# ── Publication history dates ────────────────────────────────────────────────


_JATS_WITH_DATES = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <article-id pub-id-type="doi">10.5117/X</article-id>
      <title-group><article-title>T</article-title></title-group>
      <pub-date pub-type="epub">
        <day>{pub_d}</day><month>{pub_m}</month><year>{pub_y}</year>
      </pub-date>
      <history>
        <date date-type="received">
          <day>{rec_d}</day><month>{rec_m}</month><year>{rec_y}</year>
        </date>
        <date date-type="accepted">
          <day>{acc_d}</day><month>{acc_m}</month><year>{acc_y}</year>
        </date>
      </history>
    </article-meta>
  </front>
</article>"""


def _write_dated_jats(tmp_path, *, received="2025-05-28",
                     accepted="2026-01-14", published="2026-02-16"):
    ry, rm, rd = received.split("-")
    ay, am_, ad = accepted.split("-")
    py, pm, pd = published.split("-")
    xml = _JATS_WITH_DATES.format(
        rec_y=ry, rec_m=str(int(rm)), rec_d=str(int(rd)),
        acc_y=ay, acc_m=str(int(am_)), acc_d=str(int(ad)),
        pub_y=py, pub_m=str(int(pm)), pub_d=str(int(pd)),
    )
    p = tmp_path / "article.xml"
    p.write_text(xml, encoding="utf-8")
    return str(p)


def test_dates_match(tmp_path):
    jats = _write_dated_jats(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    by_field = {r["field"]: r for r in results}
    assert by_field["date_received"]["status"] == "ok"
    assert by_field["date_accepted"]["status"] == "ok"
    assert by_field["date_published"]["status"] == "ok"


def test_date_received_mismatch(tmp_path):
    jats = _write_dated_jats(tmp_path, received="2020-01-01")
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    by_field = {r["field"]: r for r in results}
    assert by_field["date_received"]["status"] == "mismatch"
    assert by_field["date_accepted"]["status"] == "ok"


def test_date_published_skipped_when_ojs_has_none(tmp_path):
    """When OJS has no date_published the comparison is skipped (avoids a
    spurious mismatch against the today-fallback in the source)."""
    jats = _write_dated_jats(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published=None,
    )
    out = tmp_path / "comparison.json"
    compare_metadata(jats, ms, [], output_json=out)
    results = json.loads(out.read_text())
    assert not any(r["field"] == "date_published" for r in results)
