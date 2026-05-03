"""Tests for src/jatsmith/canonical_extension.py.

The fixture bundle at ``tests/fixtures/canonical_extension/`` mimics the
shape of a deployer-supplied class file (``example.cls``) plus a Quarto
extension (under ``_extensions/example-org/example/``). All fetch tests
use mocked HTTP — no live network access during the test run.
"""

from __future__ import annotations

import io
import logging
import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jatsmith import canonical_extension as ce


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "canonical_extension"
FIXTURE_CLASS_FILE = FIXTURE_DIR / "example.cls"
FIXTURE_EXTENSIONS_DIR = FIXTURE_DIR / "_extensions"


def _make_cls(path: Path, version_tag: str | None, extra: str = "") -> Path:
    """Write a minimal class-file-like file with the given ProvidesClass tag.

    ``version_tag`` is the string that will go inside the brackets of
    ``\\ProvidesClass{example}[...]``. Pass ``None`` to omit the optional
    argument entirely (so ``parse_class_version`` returns None).
    """
    header = "% Template for Example Articles (test fixture)\n"
    if version_tag is not None:
        header += f"\\ProvidesClass{{example}}[{version_tag}]\n"
    else:
        header += "\\ProvidesClass{example}\n"
    path.write_text(header + extra, encoding="utf-8")
    return path


def _seed_cache(cache_dir: Path) -> ce.CanonicalBundle:
    """Populate cache_dir with the fixture bundle and return a CanonicalBundle.

    Layout matches what fetch_canonical_bundle would produce:
        <cache_dir>/example.cls
        <cache_dir>/extensions/example-org/example/...
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE_CLASS_FILE, cache_dir / "example.cls")
    extensions_dest = cache_dir / "extensions"
    if extensions_dest.exists():
        shutil.rmtree(extensions_dest)
    shutil.copytree(FIXTURE_EXTENSIONS_DIR, extensions_dest)
    return ce.load_cached_bundle(
        cache_dir,
        "https://github.com/example-org/example-latex/blob/main/example.cls",
    )


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def test_normalize_github_blob_url():
    raw = ce.normalize_class_file_url(
        "https://github.com/owner/repo/blob/main/path/to/file.cls"
    )
    assert raw == "https://raw.githubusercontent.com/owner/repo/main/path/to/file.cls"


def test_normalize_passthrough_for_raw_url():
    url = "https://raw.githubusercontent.com/owner/repo/v1.0/file.cls"
    assert ce.normalize_class_file_url(url) == url


def test_normalize_passthrough_for_non_github():
    url = "https://example.com/static/file.cls"
    assert ce.normalize_class_file_url(url) == url


def test_normalize_strips_whitespace():
    raw = ce.normalize_class_file_url(
        "  https://github.com/o/r/blob/main/f.cls  "
    )
    assert raw == "https://raw.githubusercontent.com/o/r/main/f.cls"


def test_parse_quarto_repo_default_ref():
    assert ce.parse_quarto_repo("ccr-journal/ccr-quarto") == (
        "ccr-journal", "ccr-quarto", "main"
    )


def test_parse_quarto_repo_with_ref():
    assert ce.parse_quarto_repo("ccr-journal/ccr-quarto@v0.5") == (
        "ccr-journal", "ccr-quarto", "v0.5"
    )


def test_parse_quarto_repo_blank_returns_none():
    assert ce.parse_quarto_repo("") is None
    assert ce.parse_quarto_repo("   ") is None


def test_parse_quarto_repo_malformed_returns_none():
    assert ce.parse_quarto_repo("not-a-repo") is None
    assert ce.parse_quarto_repo("owner/") is None
    assert ce.parse_quarto_repo("/repo") is None


# ---------------------------------------------------------------------------
# Hash & version helpers (regression-equivalent of the old ccr_cls tests)
# ---------------------------------------------------------------------------


def test_parse_class_version_returns_provides_class_optional_arg(tmp_path: Path):
    cls = _make_cls(tmp_path / "example.cls", "2026-05-03 v0.04")
    assert ce.parse_class_version(cls) == "2026-05-03 v0.04"


def test_parse_class_version_missing_optional_arg_returns_none(tmp_path: Path):
    cls = _make_cls(tmp_path / "example.cls", version_tag=None)
    assert ce.parse_class_version(cls) is None


def test_parse_class_version_strips_whitespace(tmp_path: Path):
    cls = tmp_path / "example.cls"
    cls.write_text("\\ProvidesClass{example}[  2026-05-03 v0.04  ]\n", encoding="utf-8")
    assert ce.parse_class_version(cls) == "2026-05-03 v0.04"


def test_parse_class_version_handles_no_provides_class(tmp_path: Path):
    cls = tmp_path / "example.cls"
    cls.write_text("\\LoadClass{article}\n", encoding="utf-8")
    assert ce.parse_class_version(cls) is None


def test_class_sha_normalizes_crlf(tmp_path: Path):
    lf = tmp_path / "lf.cls"
    crlf = tmp_path / "crlf.cls"
    lf.write_bytes(b"\\ProvidesClass{ex}[2026-05-03 v0.05]\n\\LoadClass{article}\n")
    crlf.write_bytes(b"\\ProvidesClass{ex}[2026-05-03 v0.05]\r\n\\LoadClass{article}\r\n")
    assert ce.compute_class_sha256(lf) == ce.compute_class_sha256(crlf)


# ---------------------------------------------------------------------------
# Workspace find / install
# ---------------------------------------------------------------------------


def test_find_class_file_flat_layout(tmp_path: Path):
    cls = _make_cls(tmp_path / "example.cls", "2026-05-03 v0.05")
    assert ce.find_class_file_in_workspace(tmp_path, "example.cls") == cls


def test_find_class_file_under_extensions(tmp_path: Path):
    nested_dir = tmp_path / "_extensions" / "example-org" / "example"
    nested_dir.mkdir(parents=True)
    cls = _make_cls(nested_dir / "example.cls", "2026-05-03 v0.05")
    assert ce.find_class_file_in_workspace(tmp_path, "example.cls") == cls


def test_find_class_file_prefers_flat(tmp_path: Path):
    nested_dir = tmp_path / "_extensions" / "example-org" / "example"
    nested_dir.mkdir(parents=True)
    _make_cls(nested_dir / "example.cls", "2026-05-03 v0.05")
    flat = _make_cls(tmp_path / "example.cls", "2026-05-03 v0.05")
    assert ce.find_class_file_in_workspace(tmp_path, "example.cls") == flat


def test_install_canonical_class_file_creates_when_missing(tmp_path: Path):
    written = ce.install_canonical_class_file(
        tmp_path, FIXTURE_CLASS_FILE, "example.cls",
    )
    assert written == tmp_path / "example.cls"
    assert ce.compute_class_sha256(written) == ce.compute_class_sha256(FIXTURE_CLASS_FILE)


def test_install_canonical_class_file_overwrites_all_copies(tmp_path: Path):
    flat = _make_cls(tmp_path / "example.cls", "2024-01-01 v0.02")
    nested_dir = tmp_path / "_extensions" / "example-org" / "example"
    nested_dir.mkdir(parents=True)
    nested = _make_cls(nested_dir / "example.cls", "2024-01-01 v0.02")
    ce.install_canonical_class_file(tmp_path, FIXTURE_CLASS_FILE, "example.cls")
    canon = ce.compute_class_sha256(FIXTURE_CLASS_FILE)
    assert ce.compute_class_sha256(flat) == canon
    assert ce.compute_class_sha256(nested) == canon


# ---------------------------------------------------------------------------
# Bundle loading / discovery
# ---------------------------------------------------------------------------


def test_load_cached_bundle_empty_when_nothing_cached(tmp_path: Path):
    bundle = ce.load_cached_bundle(tmp_path, "")
    assert not bundle.is_configured
    assert not bundle.has_class_file
    assert not bundle.has_extensions


def test_load_cached_bundle_picks_up_seeded_cache(tmp_path: Path):
    bundle = _seed_cache(tmp_path)
    assert bundle.has_class_file
    assert bundle.class_filename == "example.cls"
    assert bundle.class_version == "2026-05-03 v0.05"
    assert bundle.has_extensions
    assert bundle.extension_subpaths == ("example-org/example",)
    assert bundle.extension_sha is not None
    assert bundle.extension_version == "0.05"  # from _extension.yml's version: key


def test_load_cached_bundle_class_only_no_extensions(tmp_path: Path):
    cache = tmp_path
    shutil.copy2(FIXTURE_CLASS_FILE, cache / "example.cls")
    bundle = ce.load_cached_bundle(
        cache,
        "https://github.com/example-org/example-latex/blob/main/example.cls",
    )
    assert bundle.has_class_file
    assert not bundle.has_extensions


def test_parse_extension_version_from_yaml(tmp_path: Path):
    yml = tmp_path / "_extension.yml"
    yml.write_text("title: ext\nversion: 1.2.3\nauthor: test\n", encoding="utf-8")
    assert ce.parse_extension_version(yml) == "1.2.3"


def test_parse_extension_version_quoted(tmp_path: Path):
    yml = tmp_path / "_extension.yml"
    yml.write_text('title: ext\nversion: "0.08"\n', encoding="utf-8")
    assert ce.parse_extension_version(yml) == "0.08"


def test_parse_extension_version_missing_returns_none(tmp_path: Path):
    yml = tmp_path / "_extension.yml"
    yml.write_text("title: ext\nauthor: test\n", encoding="utf-8")
    assert ce.parse_extension_version(yml) is None


def test_discover_extension_subpaths(tmp_path: Path):
    bundle_root = tmp_path / "extensions"
    (bundle_root / "org-a" / "ext-a").mkdir(parents=True)
    (bundle_root / "org-a" / "ext-a" / "_extension.yml").write_text("title: A\n")
    (bundle_root / "org-b" / "ext-b").mkdir(parents=True)
    (bundle_root / "org-b" / "ext-b" / "_extension.yml").write_text("title: B\n")
    (bundle_root / "no-marker").mkdir()
    (bundle_root / "no-marker" / "stuff.txt").write_text("not an extension")
    subs = ce.discover_extension_subpaths(bundle_root)
    assert subs == ["org-a/ext-a", "org-b/ext-b"]


# ---------------------------------------------------------------------------
# Fetch (with mocked HTTP)
# ---------------------------------------------------------------------------


def _make_fake_tarball() -> bytes:
    """Build a tarball mirroring GitHub's archive layout, containing a
    minimal _extensions/ subtree with one extension root."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        # GitHub wraps the repo root in `<repo>-<ref>/`
        for rel in (
            "_extensions/example-org/example/_extension.yml",
            "_extensions/example-org/example/example.cls",
            "_extensions/example-org/example/template.tex",
        ):
            data = (
                FIXTURE_EXTENSIONS_DIR / Path(rel.split("_extensions/")[1])
            ).read_bytes()
            info = tarfile.TarInfo(name=f"example-main/{rel}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        # Also add a noise file outside _extensions/ to verify we ignore it.
        readme = b"# Example repo\n"
        info = tarfile.TarInfo(name="example-main/README.md")
        info.size = len(readme)
        tf.addfile(info, io.BytesIO(readme))
    return buf.getvalue()


def test_fetch_class_file_only(tmp_path: Path):
    cls_url = "https://github.com/example-org/example-latex/blob/main/example.cls"
    raw_url = "https://raw.githubusercontent.com/example-org/example-latex/main/example.cls"
    fake_body = FIXTURE_CLASS_FILE.read_bytes()

    captured: list[str] = []

    def fake_get(url, timeout):
        captured.append(url)
        return fake_body

    with patch.object(ce, "_http_get", side_effect=fake_get):
        bundle = ce.fetch_canonical_bundle(cls_url, "", tmp_path)

    assert captured == [raw_url]  # HTML URL was normalized before fetch
    assert bundle.has_class_file
    assert (tmp_path / "example.cls").is_file()
    assert bundle.class_version == "2026-05-03 v0.05"
    assert not bundle.has_extensions


def test_fetch_quarto_extension_only(tmp_path: Path):
    repo_spec = "example-org/example@v0.5"
    expected_url = "https://github.com/example-org/example/archive/v0.5.tar.gz"
    fake_body = _make_fake_tarball()

    captured: list[str] = []

    def fake_get(url, timeout):
        captured.append(url)
        return fake_body

    with patch.object(ce, "_http_get", side_effect=fake_get):
        bundle = ce.fetch_canonical_bundle("", repo_spec, tmp_path)

    assert captured == [expected_url]
    assert bundle.has_extensions
    assert bundle.extension_subpaths == ("example-org/example",)
    assert (tmp_path / "extensions" / "example-org" / "example" / "_extension.yml").is_file()
    # Files outside _extensions/ are not extracted
    assert not (tmp_path / "extensions" / "README.md").exists()
    assert not (tmp_path / "extensions" / "example-org" / "example" / "README.md").exists()


def test_fetch_skips_blank_urls(tmp_path: Path):
    with patch.object(ce, "_http_get") as mock_get:
        bundle = ce.fetch_canonical_bundle("", "", tmp_path)
    assert mock_get.call_count == 0
    assert not bundle.is_configured


def test_fetch_class_file_404_falls_back_to_cache(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    # Seed cache with the fixture, then simulate a 404 on next fetch.
    _seed_cache(tmp_path)
    import urllib.error

    def raise_404(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    cls_url = "https://github.com/example-org/example-latex/blob/main/example.cls"
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        with patch.object(ce, "_http_get", side_effect=raise_404):
            bundle = ce.fetch_canonical_bundle(cls_url, "", tmp_path)

    assert any("Failed to fetch class file" in r.getMessage() for r in caplog.records)
    # Cached copy survives.
    assert bundle.has_class_file
    assert (tmp_path / "example.cls").is_file()


def test_fetch_extension_404_falls_back_to_cache(tmp_path: Path):
    _seed_cache(tmp_path)
    import urllib.error

    def raise_404(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    with patch.object(ce, "_http_get", side_effect=raise_404):
        bundle = ce.fetch_canonical_bundle("", "example-org/example", tmp_path)

    assert bundle.has_extensions
    assert (tmp_path / "extensions" / "example-org" / "example" / "_extension.yml").is_file()


def test_fetch_malformed_quarto_repo_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        with patch.object(ce, "_http_get") as mock_get:
            ce.fetch_canonical_bundle("", "not-a-valid-spec!", tmp_path)
    assert mock_get.call_count == 0
    assert any("malformed" in r.getMessage() for r in caplog.records)


def test_extract_extensions_rejects_path_traversal(tmp_path: Path):
    """Tar members trying to escape the cache dir must be skipped."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        bad = tarfile.TarInfo(name="example-main/_extensions/../escape.txt")
        bad.size = 5
        tf.addfile(bad, io.BytesIO(b"hello"))
        good = tarfile.TarInfo(
            name="example-main/_extensions/example-org/example/_extension.yml"
        )
        body = (FIXTURE_EXTENSIONS_DIR / "example-org" / "example" / "_extension.yml").read_bytes()
        good.size = len(body)
        tf.addfile(good, io.BytesIO(body))

    def fake_get(url, timeout):
        return buf.getvalue()

    with patch.object(ce, "_http_get", side_effect=fake_get):
        ce.fetch_canonical_bundle("", "example-org/example", tmp_path)

    assert not (tmp_path / "escape.txt").exists()
    assert (tmp_path / "extensions" / "example-org" / "example" / "_extension.yml").is_file()


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def test_warn_no_op_when_bundle_unconfigured(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    bundle = ce.load_cached_bundle(tmp_path, "")
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(tmp_path, bundle)
    assert caplog.records == []


def test_warn_no_op_when_no_workspace_class_file(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bundle = _seed_cache(cache)
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(workspace, bundle)
    # No class file in workspace → silent (matches old ccr_cls behaviour).
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_warn_drift_includes_both_version_strings(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bundle = _seed_cache(cache)
    _make_cls(workspace / "example.cls", "2024-01-01 v0.02")
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(workspace, bundle)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    # The workspace and canonical \ProvidesClass strings both appear in the
    # warning so the editor sees what's installed vs. what's expected.
    assert any("2024-01-01 v0.02" in w.getMessage() for w in warnings)
    assert any("2026-05-03 v0.05" in w.getMessage() for w in warnings)


def test_warn_edited_class_file(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bundle = _seed_cache(cache)
    edited = workspace / "example.cls"
    edited.write_text(
        FIXTURE_CLASS_FILE.read_text() + "\n% an author edit\n", encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(workspace, bundle)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("may have been edited" in w.getMessage() for w in warnings)


def test_warn_clean_workspace_silent(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bundle = _seed_cache(cache)
    shutil.copy2(FIXTURE_CLASS_FILE, workspace / "example.cls")
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(workspace, bundle)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_warn_extension_drift(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    bundle = _seed_cache(cache)
    # Vendor the extension into the workspace, then edit one file.
    ws_ext_dir = workspace / "_extensions" / "example-org" / "example"
    ws_ext_dir.mkdir(parents=True)
    for child in (cache / "extensions" / "example-org" / "example").iterdir():
        shutil.copy2(child, ws_ext_dir / child.name)
    (ws_ext_dir / "_extension.yml").write_text("title: hand-edited\n")
    with caplog.at_level(logging.WARNING, logger="jatsmith.canonical_extension"):
        ce.warn_if_outdated(workspace, bundle)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("differ from the canonical bundle" in w.getMessage() for w in warnings)


# ---------------------------------------------------------------------------
# Install extensions into workspace
# ---------------------------------------------------------------------------


def test_install_canonical_extensions_overwrites_stale_bundle(tmp_path: Path):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    bundle = _seed_cache(cache)
    ws_ext_dir = workspace / "_extensions" / "example-org" / "example"
    ws_ext_dir.mkdir(parents=True)
    (ws_ext_dir / "_extension.yml").write_text("stale: true\n")
    (ws_ext_dir / "orphan.tex").write_text("leftover\n")

    written = ce.install_canonical_extensions(workspace, bundle)

    assert ws_ext_dir / "_extension.yml" in written or (ws_ext_dir.is_dir() and written)
    # Stale file must be wiped (replace, not merge)
    assert not (ws_ext_dir / "orphan.tex").exists()
    yml_text = (ws_ext_dir / "_extension.yml").read_text()
    assert "stale" not in yml_text


def test_install_canonical_extensions_leaves_unrelated_extensions_alone(tmp_path: Path):
    cache = tmp_path / "cache"
    workspace = tmp_path / "ws"
    bundle = _seed_cache(cache)
    other_ext = workspace / "_extensions" / "third-party" / "extension"
    other_ext.mkdir(parents=True)
    (other_ext / "_extension.yml").write_text("title: third party\n")

    ce.install_canonical_extensions(workspace, bundle)

    # Third-party extension untouched.
    assert (other_ext / "_extension.yml").read_text() == "title: third party\n"
    # Canonical extension installed.
    assert (workspace / "_extensions" / "example-org" / "example" / "_extension.yml").is_file()


def test_install_canonical_extensions_noop_for_empty_bundle(tmp_path: Path):
    bundle = ce.load_cached_bundle(tmp_path / "cache", "")
    written = ce.install_canonical_extensions(tmp_path / "ws", bundle)
    assert written == []
