import shutil
import unicodedata
from pathlib import Path

import pytest

from jatsmith import canonical_extension as ce
from jatsmith.prepare_source import _normalize_bbl, _parse_latex_log_errors, prepare_workspace
from jatsmith.quarto import prepare_quarto_workspace


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "canonical_extension"


@pytest.fixture
def seeded_bundle(tmp_path: Path):
    """Drop the fixture bundle into a cache dir, expose it via
    ``set_current_bundle``, and yield it for the test. Restored to None
    on teardown so other tests aren't polluted.
    """
    cache = tmp_path / "_canon_cache"
    cache.mkdir()
    shutil.copy2(_FIXTURE_DIR / "example.cls", cache / "example.cls")
    shutil.copytree(_FIXTURE_DIR / "_extensions", cache / "extensions")
    bundle = ce.load_cached_bundle(
        cache,
        "https://github.com/example-org/example-latex/blob/main/example.cls",
    )
    prev = ce.get_current_bundle()
    ce.set_current_bundle(bundle)
    try:
        yield bundle
    finally:
        ce.set_current_bundle(prev)


class TestNormalizeBbl:
    def test_normalizes_combining_accent_with_precomposed(self, tmp_path: Path):
        """Decomposed e + combining acute → precomposed é via NFC."""
        bbl = tmp_path / "main.bbl"
        decomposed = "Garc\u0065\u0301a"  # e + combining acute
        bbl.write_text(decomposed, encoding="utf-8")

        _normalize_bbl(tmp_path)

        result = bbl.read_text(encoding="utf-8")
        assert result == "Garc\u00e9a"  # precomposed é
        assert "\u0301" not in result

    def test_warns_on_unresolvable_combining_mark(self, tmp_path: Path, caplog):
        """Dotless-i + combining acute has no NFC form — warn, don't strip."""
        bbl = tmp_path / "main.bbl"
        # dotless-i (U+0131) + combining acute accent (U+0301) has no NFC form
        decomposed = "Mach\u0131\u0301o-Regidor"
        bbl.write_text(decomposed, encoding="utf-8")

        _normalize_bbl(tmp_path)

        result = bbl.read_text(encoding="utf-8")
        # Combining mark is preserved (not stripped)
        assert "\u0301" in result
        assert "remaining combining mark" in caplog.text

    def test_already_nfc_unchanged(self, tmp_path: Path):
        bbl = tmp_path / "main.bbl"
        text = "Normal ASCII text with no combining chars\n"
        bbl.write_text(text, encoding="utf-8")

        _normalize_bbl(tmp_path)

        assert bbl.read_text(encoding="utf-8") == text

    def test_no_bbl_is_noop(self, tmp_path: Path):
        """No error when main.bbl doesn't exist."""
        _normalize_bbl(tmp_path)


class TestParseLatexLogErrors:
    def test_detects_undefined_control_sequence(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "Some preamble output.\n"
            "! Undefined control sequence.\n"
            "l.51 \\addbibresource\n"
            "                    {bibliography.bib}\n"
            "The control sequence at the end of the top line\n"
        )

        fatal, errors = _parse_latex_log_errors(log)

        assert fatal == []
        assert len(errors) == 1
        assert "Undefined control sequence" in errors[0]
        assert "l.51" in errors[0]

    def test_dedups_repeated_errors(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "\n".join(["! Undefined control sequence."] * 50) + "\n"
        )

        _, errors = _parse_latex_log_errors(log)

        assert len(errors) == 1

    def test_flags_no_pages_fatal(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "! Emergency stop.\n"
            "\n"
            "No pages of output.\n"
            "Transcript written on main.log.\n"
        )

        fatal, _ = _parse_latex_log_errors(log)

        assert "! Emergency stop." in fatal
        assert "No pages of output." in fatal

    def test_ignores_latex_warnings(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "LaTeX Warning: Reference `foo' on page 3 undefined on input line 17.\n"
            "Overfull \\hbox (8.21pt too wide) in paragraph at lines 42--44\n"
            "Package hyperref Warning: Token not allowed in a PDF string.\n"
        )

        fatal, errors = _parse_latex_log_errors(log)

        assert fatal == []
        assert errors == []

    def test_caps_at_ten_errors(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "\n".join(f"! Error number {i}." for i in range(20)) + "\n"
        )

        _, errors = _parse_latex_log_errors(log)

        assert len(errors) == 10

    def test_missing_log_returns_empty(self, tmp_path: Path):
        fatal, errors = _parse_latex_log_errors(tmp_path / "does-not-exist.log")
        assert fatal == []
        assert errors == []

    def test_hundred_errors_cap_is_fatal(self, tmp_path: Path):
        log = tmp_path / "main.log"
        log.write_text(
            "! Undefined control sequence.\n"
            "(That makes 100 errors; please try again.)\n"
        )

        fatal, _ = _parse_latex_log_errors(log)

        assert "(That makes 100 errors; please try again.)" in fatal


# ── Canonical-bundle install path ──────────────────────────────────────────────
#
# These tests pin the wiring between the SiteConfig-driven canonical-bundle
# fetch and what actually lands in the workspace before LaTeX/Quarto runs.
# Skipping them would let a refactor silently disconnect the toggle from the
# pipeline (the failure mode that prompted the user to ask "did you actually
# test this end-to-end?").


class TestPrepareWorkspaceUsesCanonicalBundle:
    def _seed_source_with_stale_class(self, source: Path) -> None:
        source.mkdir()
        (source / "main.tex").write_text(
            "\\documentclass{example}\n\\begin{document}\nhi\n\\end{document}\n",
            encoding="utf-8",
        )
        # Stale class file the toggle should overwrite.
        (source / "example.cls").write_text(
            "% stale, hand-edited by author\n"
            "\\ProvidesClass{example}[2020-01-01 v0.01]\n"
            "\\LoadClass{article}\n",
            encoding="utf-8",
        )

    def test_toggle_on_overwrites_stale_class_with_canonical(
        self, tmp_path: Path, seeded_bundle,
    ):
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_source_with_stale_class(source)

        prepare_workspace(source, ws, use_canonical_class_file=True)

        installed = (ws / "example.cls").read_text(encoding="utf-8")
        # Canonical version landed; stale version is gone. The file may have
        # additional pipeline patches prepended (\pdfminorversion=7, pstricks
        # comment-out) — those are applied by ``_patch_class_file`` *after*
        # the canonical install, which is the intended order.
        assert "2026-05-03 v0.05" in installed
        assert "2020-01-01 v0.01" not in installed
        assert "stale, hand-edited" not in installed

    def test_toggle_off_leaves_stale_class_untouched(
        self, tmp_path: Path, seeded_bundle,
    ):
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_source_with_stale_class(source)

        prepare_workspace(source, ws, use_canonical_class_file=False)

        # The stale version stays — the only edits should come from
        # _patch_class_file (\pdfminorversion + pstricks comment-out), neither
        # of which touches \ProvidesClass.
        installed = (ws / "example.cls").read_text(encoding="utf-8")
        assert "2020-01-01 v0.01" in installed
        assert "v0.05" not in installed

    def test_no_bundle_configured_is_safe_noop(self, tmp_path: Path):
        """When no bundle is set (e.g. CLI without STORAGE_DIR), turning the
        toggle on must not raise — the install is just skipped."""
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_source_with_stale_class(source)
        ce.set_current_bundle(None)

        # Should not raise.
        prepare_workspace(source, ws, use_canonical_class_file=True)
        assert (ws / "example.cls").is_file()  # workspace still copied
        # Stale content survives — we have nothing canonical to swap in.
        assert "v0.01" in (ws / "example.cls").read_text(encoding="utf-8")


class TestPrepareQuartoWorkspaceUsesCanonicalBundle:
    def _seed_quarto_source_with_stale_extension(self, source: Path) -> None:
        source.mkdir()
        (source / "paper.qmd").write_text(
            "---\ntitle: t\nformat: example-pdf\n---\n# Body\n",
            encoding="utf-8",
        )
        ext_dir = source / "_extensions" / "example-org" / "example"
        ext_dir.mkdir(parents=True)
        # Stale extension — different content, different `version`.
        (ext_dir / "_extension.yml").write_text(
            "title: Stale ext\nversion: 0.01\n", encoding="utf-8",
        )
        (ext_dir / "example.cls").write_text(
            "% stale class file\n"
            "\\ProvidesClass{example}[2020-01-01 v0.01]\n",
            encoding="utf-8",
        )
        # Orphan file the canonical install must wipe (sync, not merge).
        (ext_dir / "orphan.tex").write_text("leftover\n", encoding="utf-8")

    def test_toggle_on_overwrites_stale_extension_with_canonical(
        self, tmp_path: Path, seeded_bundle,
    ):
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_quarto_source_with_stale_extension(source)

        prepare_quarto_workspace(source, ws, use_canonical_class_file=True)

        ext_dir = ws / "_extensions" / "example-org" / "example"
        yml = (ext_dir / "_extension.yml").read_text(encoding="utf-8")
        assert "version: 0.05" in yml or 'version: "0.05"' in yml, (
            "workspace _extension.yml not replaced with canonical"
        )
        assert "Stale" not in yml
        # Orphan file must be gone — install replaces, not merges.
        assert not (ext_dir / "orphan.tex").exists()
        # Canonical class file is in place.
        cls_content = (ext_dir / "example.cls").read_text(encoding="utf-8")
        assert "v0.05" in cls_content
        assert "v0.01" not in cls_content

    def test_toggle_off_leaves_stale_extension_untouched(
        self, tmp_path: Path, seeded_bundle,
    ):
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_quarto_source_with_stale_extension(source)

        prepare_quarto_workspace(source, ws, use_canonical_class_file=False)

        ext_dir = ws / "_extensions" / "example-org" / "example"
        yml = (ext_dir / "_extension.yml").read_text(encoding="utf-8")
        assert "Stale ext" in yml
        assert (ext_dir / "orphan.tex").is_file()  # not pruned
        cls_content = (ext_dir / "example.cls").read_text(encoding="utf-8")
        assert "v0.01" in cls_content
        assert "v0.05" not in cls_content

    def test_no_bundle_configured_is_safe_noop(self, tmp_path: Path):
        source = tmp_path / "src"
        ws = tmp_path / "ws"
        self._seed_quarto_source_with_stale_extension(source)
        ce.set_current_bundle(None)

        prepare_quarto_workspace(source, ws, use_canonical_class_file=True)

        # Workspace was copied; stale extension survives because no canonical
        # was available to overwrite it.
        ext_dir = ws / "_extensions" / "example-org" / "example"
        assert ext_dir.is_dir()
        assert "Stale" in (ext_dir / "_extension.yml").read_text(encoding="utf-8")
