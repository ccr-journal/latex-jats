from pathlib import Path

import pytest

from latex_jats.convert import _warn_stray_text_after_includegraphics


def test_trailing_period_triggers_warning(tmp_path, caplog):
    tex = tmp_path / "main.tex"
    tex.write_text(r"\includegraphics[width=\linewidth]{img.png}.")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(tex)
    assert any("Stray text" in r.message and "'.' " in r.message for r in caplog.records)


def test_trailing_comma_triggers_warning(tmp_path, caplog):
    tex = tmp_path / "main.tex"
    tex.write_text(r"\includegraphics{img.png},")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(tex)
    assert any("Stray text" in r.message for r in caplog.records)


def test_no_trailing_text_no_warning(tmp_path, caplog):
    tex = tmp_path / "main.tex"
    tex.write_text(r"\includegraphics[width=\linewidth]{img.png}")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(tex)
    assert not caplog.records


def test_comment_after_includegraphics_no_warning(tmp_path, caplog):
    tex = tmp_path / "main.tex"
    tex.write_text(r"\includegraphics{img.png}% comment")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(tex)
    assert not caplog.records


def test_input_files_scanned(tmp_path, caplog):
    main = tmp_path / "main.tex"
    child = tmp_path / "body.tex"
    main.write_text(r"\input{body}")
    child.write_text(r"\includegraphics{img.png}.")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(main)
    assert any("body.tex" in r.message for r in caplog.records)


def test_reports_line_number(tmp_path, caplog):
    tex = tmp_path / "main.tex"
    tex.write_text("line1\nline2\n\\includegraphics{img.png}.\nline4\n")
    with caplog.at_level("WARNING"):
        _warn_stray_text_after_includegraphics(tex)
    assert any(":3" in r.message for r in caplog.records)
