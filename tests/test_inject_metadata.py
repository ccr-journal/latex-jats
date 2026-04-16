"""Unit tests for inject_ojs_metadata: injecting OJS metadata into LaTeX preamble."""

from dataclasses import dataclass
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
