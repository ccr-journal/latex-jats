"""Unit tests for inject_ojs_metadata: injecting OJS metadata into LaTeX preamble."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest


# ── Lightweight stand-in for Manuscript model ────────────────────────────────


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


# Import after dataclass definition so we can use it
from web.backend.app.worker import inject_ojs_metadata


_TEX_TEMPLATE = r"""\documentclass{{ccr}}
\title{{A Title}}
{preamble}
\begin{{document}}
Hello world.
\end{{document}}
"""


def _write_tex(tmp_path, preamble_lines=""):
    p = tmp_path / "main.tex"
    p.write_text(_TEX_TEMPLATE.format(preamble=preamble_lines), encoding="utf-8")
    return p


def test_inject_all_missing(tmp_path):
    """All macros are injected when none are present."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.YAO",
        volume="7",
        issue_number="1",
        year=2025,
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert r"\doi{10.5117/CCR2025.1.2.YAO}" in text
    assert r"\volume{7}" in text
    assert r"\pubnumber{1}" in text
    assert r"\pubyear{2025}" in text
    assert r"\firstpage{1}" in text
    # Injected block appears before \begin{document}
    assert text.index(r"\doi{") < text.index(r"\begin{document}")


def test_no_overwrite_existing(tmp_path):
    """Existing macros are left untouched."""
    tex = _write_tex(tmp_path, preamble_lines=r"\doi{10.5117/CCR2025.1.99.OLD}" + "\n" + r"\volume{99}")
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.NEW",
        volume="7",
        issue_number="1",
        year=2025,
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    # Original values preserved
    assert r"\doi{10.5117/CCR2025.1.99.OLD}" in text
    assert r"\volume{99}" in text
    # Missing ones still injected
    assert r"\pubnumber{1}" in text
    assert r"\pubyear{2025}" in text


def test_none_fields_skipped(tmp_path):
    """Fields that are None in the manuscript are not injected."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(doi="10.5117/CCR2025.1.2.YAO")  # only doi set
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert r"\doi{10.5117/CCR2025.1.2.YAO}" in text
    assert r"\volume{" not in text
    assert r"\pubnumber{" not in text
    assert r"\pubyear{" not in text
    # firstpage is always injected (default "1")
    assert r"\firstpage{1}" in text


def test_no_begin_document(tmp_path):
    """File without \\begin{document} is left unchanged."""
    tex = tmp_path / "main.tex"
    original = r"\documentclass{ccr}" + "\n" + r"\title{Hi}"
    tex.write_text(original, encoding="utf-8")
    ms = FakeManuscript(doi="10.5117/CCR2025.1.2.YAO")
    inject_ojs_metadata(tex, ms)
    assert tex.read_text() == original


def test_document_content_preserved(tmp_path):
    """Document body is not altered by injection."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(doi="10.5117/CCR2025.1.2.YAO")
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert "Hello world." in text
    assert r"\end{document}" in text


# ── Date injection ───────────────────────────────────────────────────────────


def test_inject_all_dates_present(tmp_path):
    """All three date macros are injected when all three dates are set."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert r"\datereceived{2025-05-28}" in text
    assert r"\dateaccepted{2026-01-14}" in text
    assert r"\datepublished{2026-02-16}" in text


def test_skip_all_dates_when_accepted_missing(tmp_path):
    """No date macros injected when date_accepted is unset (all-or-nothing)."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(
        doi="10.5117/CCR2025.1.2.YAO",
        date_received="2025-05-28",
        date_accepted=None,
        date_published="2026-02-16",
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert r"\datereceived" not in text
    assert r"\dateaccepted" not in text
    assert r"\datepublished" not in text
    # Other injections still work
    assert r"\doi{10.5117/CCR2025.1.2.YAO}" in text


def test_datepublished_falls_back_to_today(tmp_path):
    """Missing date_published falls back to today's date at injection time."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published=None,
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert rf"\datepublished{{{today}}}" in text
    assert r"\datereceived{2025-05-28}" in text
    assert r"\dateaccepted{2026-01-14}" in text


def test_datereceived_falls_back_to_today(tmp_path):
    """Missing date_received also falls back to today (defensive; rare in practice)."""
    tex = _write_tex(tmp_path)
    ms = FakeManuscript(
        date_received=None,
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert rf"\datereceived{{{today}}}" in text


def test_existing_date_macros_not_overwritten(tmp_path):
    """Dates already in the preamble are left untouched."""
    tex = _write_tex(
        tmp_path,
        preamble_lines=r"\datereceived{2020-01-01}" + "\n" + r"\dateaccepted{2020-02-02}",
    )
    ms = FakeManuscript(
        date_received="2025-05-28",
        date_accepted="2026-01-14",
        date_published="2026-02-16",
    )
    inject_ojs_metadata(tex, ms)
    text = tex.read_text()
    assert r"\datereceived{2020-01-01}" in text
    assert r"\dateaccepted{2020-02-02}" in text
    # date_published was not already set → injected from manuscript
    assert r"\datepublished{2026-02-16}" in text
