"""Unit tests for Quarto-side OJS metadata injection.

Mirrors tests/test_inject_metadata.py one-to-one, but operates on QMD
YAML front matter rather than a LaTeX preamble.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from jatsmith.quarto import parse_qmd_frontmatter, upsert_qmd_frontmatter_keys
from web.backend.app.worker import inject_ojs_metadata_qmd


@dataclass
class FakeManuscript:
    doi: Optional[str] = None
    volume: Optional[str] = None
    issue_number: Optional[str] = None
    year: Optional[int] = None
    date_received: Optional[str] = None
    date_accepted: Optional[str] = None
    date_published: Optional[str] = None
    ojs_submission_id: Optional[int] = 1


_QMD_TEMPLATE = """---
title: "A Title"
{extra}---

# Body

Some text.
"""


def _write_qmd(tmp_path, extra=""):
    p = tmp_path / "article.qmd"
    p.write_text(_QMD_TEMPLATE.format(extra=extra), encoding="utf-8")
    return p


# ── inject_ojs_metadata_qmd (ORM wrapper) ────────────────────────────────────


def test_inject_all_missing(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.YAO",
        volume="7",
        issue_number="1",
        year=2025,
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/CCR2025.1.2.YAO"
    assert meta["volume"] == "7"
    assert meta["pubnumber"] == "1"
    assert meta["pubyear"] == "2025"
    assert meta["firstpage"] == "1"


def test_no_overwrite_existing(tmp_path):
    qmd = _write_qmd(tmp_path, extra='doi: "10.5117/CCR2025.1.99.OLD"\nvolume: "99"\n')
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.NEW",
        volume="7",
        issue_number="1",
        year=2025,
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    # Original values preserved
    assert meta["doi"] == "10.5117/CCR2025.1.99.OLD"
    assert meta["volume"] == "99"
    # Missing ones still injected
    assert meta["pubnumber"] == "1"
    assert meta["pubyear"] == "2025"


def test_none_fields_skipped(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(doi="10.5117/CCR2025.1.2.YAO")
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/CCR2025.1.2.YAO"
    assert "volume" not in meta
    assert "pubnumber" not in meta
    assert "pubyear" not in meta
    # firstpage always injected with default "1"
    assert meta["firstpage"] == "1"


def test_document_content_preserved(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(doi="10.5117/CCR2025.1.2.YAO")
    inject_ojs_metadata_qmd(qmd, ms)
    text = qmd.read_text(encoding="utf-8")
    assert "# Body" in text
    assert "Some text." in text


# ── Date injection ───────────────────────────────────────────────────────────


def test_inject_all_dates_present(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    assert meta["date-received"] == "2025-05-28"
    assert meta["date-accepted"] == "2026-01-14"
    assert meta["date-published"] == "2026-02-16"


def test_skip_all_dates_when_accepted_missing(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.YAO",
        date_received="2025-05-28",
        date_accepted=None,
        date_published="2026-02-16",
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    assert "date-received" not in meta
    assert "date-accepted" not in meta
    assert "date-published" not in meta
    assert meta["doi"] == "10.5117/CCR2025.1.2.YAO"


def test_datepublished_falls_back_to_today(tmp_path):
    qmd = _write_qmd(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published=None,
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert meta["date-published"] == today
    assert meta["date-received"] == "2025-05-28"
    assert meta["date-accepted"] == "2026-01-14"


def test_existing_date_keys_not_overwritten(tmp_path):
    qmd = _write_qmd(
        tmp_path,
        extra='date-received: "2020-01-01"\ndate-accepted: "2020-02-02"\n',
    )
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    inject_ojs_metadata_qmd(qmd, ms)
    meta = parse_qmd_frontmatter(qmd)
    assert meta["date-received"] == "2020-01-01"
    assert meta["date-accepted"] == "2020-02-02"
    # Not previously set → inserted from manuscript
    assert meta["date-published"] == "2026-02-16"


# ── upsert_qmd_frontmatter_keys (pure helper) ────────────────────────────────


def test_no_frontmatter(tmp_path):
    """QMD without --- fences is left unchanged."""
    qmd = tmp_path / "article.qmd"
    original = "# No Front Matter\n\nJust body.\n"
    qmd.write_text(original, encoding="utf-8")
    inserted = upsert_qmd_frontmatter_keys(qmd, {"doi": "10.5117/X"})
    assert inserted == []
    assert qmd.read_text(encoding="utf-8") == original


def test_empty_frontmatter(tmp_path):
    """Empty front matter block ---\\n--- gets keys inserted cleanly."""
    qmd = tmp_path / "article.qmd"
    qmd.write_text("---\n---\n\n# Body\n", encoding="utf-8")
    inserted = upsert_qmd_frontmatter_keys(
        qmd, {"doi": "10.5117/CCR.X", "volume": "7"}
    )
    assert inserted == ["doi", "volume"]
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/CCR.X"
    assert meta["volume"] == "7"
    assert "# Body" in qmd.read_text(encoding="utf-8")


def test_empty_value_treated_as_missing(tmp_path):
    """key: (empty) is treated as missing and gets filled.

    Matches LaTeX parity: inject_ojs_metadata checks for macro presence
    via regex, not content; parse_qmd_frontmatter drops empty scalars.
    """
    qmd = _write_qmd(tmp_path, extra="doi:\n")
    inserted = upsert_qmd_frontmatter_keys(qmd, {"doi": "10.5117/CCR.NEW"})
    assert inserted == ["doi"]
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/CCR.NEW"


def test_numeric_values_quoted(tmp_path):
    """Numeric-looking strings round-trip as strings, not ints."""
    qmd = _write_qmd(tmp_path)
    upsert_qmd_frontmatter_keys(qmd, {"volume": "01"})
    meta = parse_qmd_frontmatter(qmd)
    assert meta["volume"] == "01"
    assert not isinstance(meta["volume"], int)


def test_trailing_whitespace_on_closing_fence(tmp_path):
    """Closing --- with trailing whitespace is recognised."""
    qmd = tmp_path / "article.qmd"
    qmd.write_text('---\ntitle: "T"\n---   \n\n# Body\n', encoding="utf-8")
    inserted = upsert_qmd_frontmatter_keys(qmd, {"doi": "10.5117/X"})
    assert inserted == ["doi"]
    meta = parse_qmd_frontmatter(qmd)
    assert meta["doi"] == "10.5117/X"
