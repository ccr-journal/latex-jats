import unicodedata
from pathlib import Path

from latex_jats.prepare_source import _normalize_bbl, _parse_latex_log_errors


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
