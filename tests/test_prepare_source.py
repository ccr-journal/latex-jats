import unicodedata
from pathlib import Path

from latex_jats.prepare_source import _normalize_bbl


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
