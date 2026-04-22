"""Tests for src/latex_jats/ccr_cls.py."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from latex_jats.ccr_cls import (
    CANONICAL_CCR_CLS_PATH,
    CANONICAL_EXTENSION_DIR,
    EXPECTED_CCR_CLS_SHA256,
    EXPECTED_CCR_CLS_VERSION,
    EXPECTED_EXTENSION_SHA256,
    compute_ccr_cls_sha256,
    compute_extension_sha256,
    find_ccr_cls,
    find_ccr_extension,
    install_canonical_ccr_cls,
    install_canonical_ccr_extension,
    parse_ccr_cls_version,
    warn_if_outdated,
)


CANONICAL_FIXTURE = CANONICAL_CCR_CLS_PATH


def _make_cls(path: Path, version: str | None, extra: str = "") -> Path:
    """Write a minimal ccr.cls-like file with a given version comment."""
    header = "% Template for CCR Articles (very WIP)\n"
    if version is not None:
        header += f"% Version {version}\n"
    header += (
        "% Please see https://github.com/ccr-journal/ccr-latex\n"
        "\n"
        "\\ProvidesClass{ccr}[2023-02-03 v0.01]\n"
    )
    path.write_text(header + extra, encoding="utf-8")
    return path


# --- pinned constants sanity --------------------------------------------------


def test_canonical_fixture_has_parseable_version():
    """The committed canonical fixture must have a parseable % Version comment;
    EXPECTED_CCR_CLS_VERSION is derived from it at import time."""
    assert parse_ccr_cls_version(CANONICAL_FIXTURE) is not None
    assert EXPECTED_CCR_CLS_VERSION == parse_ccr_cls_version(CANONICAL_FIXTURE)


def test_canonical_providesclass_matches_version_comment():
    """The \\ProvidesClass[... vX.XX] tag should match the % Version comment.
    They drift easily under hand edits — catch it loudly."""
    text = CANONICAL_FIXTURE.read_text(encoding="utf-8")
    import re
    m = re.search(r"\\ProvidesClass\{ccr\}\[.*?v(\d+(?:\.\d+)+)\]", text)
    assert m is not None, "no \\ProvidesClass[...vX.XX] tag in canonical"
    assert m.group(1) == EXPECTED_CCR_CLS_VERSION, (
        f"\\ProvidesClass says v{m.group(1)} but % Version says v{EXPECTED_CCR_CLS_VERSION}"
    )


# --- find_ccr_cls -------------------------------------------------------------


def test_find_flat_layout(tmp_path: Path):
    cls = _make_cls(tmp_path / "ccr.cls", "0.05")
    assert find_ccr_cls(tmp_path) == cls


def test_find_quarto_extension_layout(tmp_path: Path):
    ext_dir = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    ext_dir.mkdir(parents=True)
    cls = _make_cls(ext_dir / "ccr.cls", "0.05")
    assert find_ccr_cls(tmp_path) == cls


def test_find_none_when_missing(tmp_path: Path):
    assert find_ccr_cls(tmp_path) is None


def test_find_prefers_flat_over_extension(tmp_path: Path):
    flat = _make_cls(tmp_path / "ccr.cls", "0.05")
    ext_dir = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    ext_dir.mkdir(parents=True)
    _make_cls(ext_dir / "ccr.cls", "0.05")
    assert find_ccr_cls(tmp_path) == flat


# --- parse_ccr_cls_version ----------------------------------------------------


def test_parse_version_matches(tmp_path: Path):
    cls = _make_cls(tmp_path / "ccr.cls", "0.04")
    assert parse_ccr_cls_version(cls) == "0.04"


def test_parse_version_missing_returns_none(tmp_path: Path):
    cls = _make_cls(tmp_path / "ccr.cls", version=None)
    assert parse_ccr_cls_version(cls) is None


# --- warn_if_outdated ---------------------------------------------------------


def test_old_version_emits_upgrade_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    _make_cls(tmp_path / "ccr.cls", "0.02")
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "v0.02" in msg
    assert f"v{EXPECTED_CCR_CLS_VERSION}" in msg
    assert "upgrade" in msg.lower()


def test_old_version_in_quarto_extension_layout(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    ext_dir = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    ext_dir.mkdir(parents=True)
    _make_cls(ext_dir / "ccr.cls", "0.04")
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    # Two warnings: the cls version and the bundle drift (bare extension dir).
    assert any("v0.04" in w.getMessage() for w in warnings), \
        f"expected a version warning, got {[w.getMessage() for w in warnings]}"
    assert any("extension" in w.getMessage() for w in warnings), \
        f"expected an extension drift warning, got {[w.getMessage() for w in warnings]}"


def test_canonical_content_no_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    dest = tmp_path / "ccr.cls"
    dest.write_bytes(CANONICAL_FIXTURE.read_bytes())
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_edited_canonical_emits_soft_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    dest = tmp_path / "ccr.cls"
    dest.write_text(
        CANONICAL_FIXTURE.read_text(encoding="utf-8") + "\n% an author edit\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "may have been edited" in msg
    assert f"v{EXPECTED_CCR_CLS_VERSION}" in msg


def test_canonical_crlf_no_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    dest = tmp_path / "ccr.cls"
    text = CANONICAL_FIXTURE.read_text(encoding="utf-8")
    dest.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_newer_version_no_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """If an author is ahead of our pin (e.g. picked up a new upstream first),
    don't bother them with a warning."""
    future = _bump(EXPECTED_CCR_CLS_VERSION)
    _make_cls(tmp_path / "ccr.cls", future)
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_missing_version_comment_info_only(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    _make_cls(tmp_path / "ccr.cls", version=None)
    with caplog.at_level(logging.INFO, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("skipping CCR class version check" in r.getMessage() for r in infos)


def test_no_ccr_cls_silent(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert caplog.records == []


def _bump(version: str) -> str:
    """Return a version one minor above `version` (e.g. 0.05 → 0.06)."""
    parts = [int(p) for p in version.split(".")]
    parts[-1] += 1
    return ".".join(str(p) for p in parts)


# --- install_canonical_ccr_cls -----------------------------------------------


def test_install_overwrites_flat_layout(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    _make_cls(tmp_path / "ccr.cls", "0.02", extra="% custom edit\n")
    install_canonical_ccr_cls(tmp_path)
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_install_overwrites_quarto_extension_layout(tmp_path: Path):
    ext_dir = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    ext_dir.mkdir(parents=True)
    _make_cls(ext_dir / "ccr.cls", "0.02")
    written = install_canonical_ccr_cls(tmp_path)
    assert written == ext_dir / "ccr.cls"
    assert compute_ccr_cls_sha256(written) == EXPECTED_CCR_CLS_SHA256


def test_install_creates_when_missing(tmp_path: Path):
    written = install_canonical_ccr_cls(tmp_path)
    assert written == tmp_path / "ccr.cls"
    assert compute_ccr_cls_sha256(written) == EXPECTED_CCR_CLS_SHA256


def test_install_overwrites_both_copies(tmp_path: Path):
    """Quarto submissions have ccr.cls at both the workspace root and inside
    _extensions; install must sync both or PDF compile uses the stale copy."""
    ext_dir = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    ext_dir.mkdir(parents=True)
    _make_cls(tmp_path / "ccr.cls", "0.02")
    _make_cls(ext_dir / "ccr.cls", "0.02")
    install_canonical_ccr_cls(tmp_path)
    assert compute_ccr_cls_sha256(tmp_path / "ccr.cls") == EXPECTED_CCR_CLS_SHA256
    assert compute_ccr_cls_sha256(ext_dir / "ccr.cls") == EXPECTED_CCR_CLS_SHA256


# --- install_canonical_ccr_extension -----------------------------------------


def test_canonical_bundle_has_expected_files():
    """The canonical bundle must ship the files Quarto expects. Catch anyone
    accidentally removing a partial or the class file."""
    required = [
        "ccr.cls", "ccrtemplate.tex", "ccr.lua", "_extension.yml",
        "aup_logo.pdf",
        "partials/before-body.tex", "partials/title.tex",
    ]
    for rel in required:
        assert (CANONICAL_EXTENSION_DIR / rel).is_file(), \
            f"canonical bundle missing {rel}"


def test_install_extension_creates_bundle_when_absent(tmp_path: Path):
    install_canonical_ccr_extension(tmp_path)
    ext = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    assert ext.is_dir()
    assert compute_extension_sha256(ext) == EXPECTED_EXTENSION_SHA256


def test_install_extension_overwrites_stale_bundle(tmp_path: Path):
    ext = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    (ext / "partials").mkdir(parents=True)
    _make_cls(ext / "ccr.cls", "0.02")  # stale
    (ext / "_extension.yml").write_text("stale: true\n", encoding="utf-8")
    (ext / "orphan.tex").write_text("leftover\n", encoding="utf-8")

    install_canonical_ccr_extension(tmp_path)

    assert compute_extension_sha256(ext) == EXPECTED_EXTENSION_SHA256
    assert not (ext / "orphan.tex").exists(), \
        "install should wipe leftover files, not merge"


def test_install_extension_also_syncs_flat_cls(tmp_path: Path):
    """Mixed layout: both _extensions/.../ccr.cls and a flat ccr.cls exist.
    install_canonical_ccr_extension must sync both."""
    ext = tmp_path / "_extensions" / "ccr-journal" / "ccr"
    (ext / "partials").mkdir(parents=True)
    _make_cls(tmp_path / "ccr.cls", "0.02")
    _make_cls(ext / "ccr.cls", "0.02")
    install_canonical_ccr_extension(tmp_path)
    assert compute_ccr_cls_sha256(tmp_path / "ccr.cls") == EXPECTED_CCR_CLS_SHA256
    assert compute_ccr_cls_sha256(ext / "ccr.cls") == EXPECTED_CCR_CLS_SHA256


# --- extension drift warning -------------------------------------------------


def _install_clean_extension(workspace: Path) -> Path:
    install_canonical_ccr_extension(workspace)
    return workspace / "_extensions" / "ccr-journal" / "ccr"


def test_clean_bundle_no_drift_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    _install_clean_extension(tmp_path)
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_edited_bundle_file_triggers_drift_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    ext = _install_clean_extension(tmp_path)
    (ext / "partials" / "before-body.tex").write_text("% hand-edited\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="latex_jats.ccr_cls"):
        warn_if_outdated(tmp_path)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("extension" in w.getMessage() for w in warnings), \
        f"expected extension drift warning, got {[w.getMessage() for w in warnings]}"


def test_find_extension_returns_dir_when_present(tmp_path: Path):
    _install_clean_extension(tmp_path)
    assert find_ccr_extension(tmp_path) == tmp_path / "_extensions" / "ccr-journal" / "ccr"


def test_find_extension_none_when_absent(tmp_path: Path):
    assert find_ccr_extension(tmp_path) is None
