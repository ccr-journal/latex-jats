from jatsmith.convert import _warn_text_in_figure


FIG_OPEN = "\\begin{figure}[ht!]\n"
FIG_STAR_OPEN = "\\begin{figure*}[ht!]\n"
FIG_CLOSE = "\\end{figure}\n"
FIG_STAR_CLOSE = "\\end{figure*}\n"


def _write(tmp_path, contents):
    tex = tmp_path / "main.tex"
    tex.write_text(contents)
    return tex


def test_textbf_at_top_level_warns(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_STAR_OPEN
        + "    \\centering\n"
        + "    \\textbf{(A) Top 6 channels}\\\\\n"
        + "    \\subfloat[A]{\\includegraphics{a.png}}\n"
        + "    \\caption{Caption.}\n"
        + FIG_STAR_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    msgs = [r.message for r in caplog.records]
    assert any("\\textbf at top level of figure" in m for m in msgs), msgs


def test_textbf_inside_subfloat_caption_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_STAR_OPEN
        + "    \\centering\n"
        + "    \\subfloat[\\centering \\textbf{COVID-19} (peak 25\\%)]"
          "{\\includegraphics{a.png}}\n"
        + "    \\caption{Caption.}\n"
        + FIG_STAR_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not [r for r in caplog.records if "figure" in r.message]


def test_textbf_inside_caption_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_OPEN
        + "    \\centering\n"
        + "    \\includegraphics{a.png}\n"
        + "    \\caption{See \\textbf{Table 1} for details.}\n"
        + FIG_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not caplog.records


def test_clean_figure_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_OPEN
        + "    \\centering\n"
        + "    \\includegraphics[width=\\linewidth]{a.png}\n"
        + "    \\caption{A clean figure.}\n"
        + "    \\label{fig:foo}\n"
        + FIG_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not caplog.records


def test_makebox_around_includegraphics_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_OPEN
        + "    \\centering\n"
        + "    \\makebox[\\textwidth]{\\includegraphics[width=1.2\\textwidth]{a.png}}\n"
        + "    \\caption{Wider figure.}\n"
        + FIG_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not caplog.records


def test_bare_text_at_top_level_warns(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_OPEN
        + "    Some heading text here\n"
        + "    \\includegraphics{a.png}\n"
        + "    \\caption{Caption.}\n"
        + FIG_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    msgs = [r.message for r in caplog.records]
    assert any("Bare text in figure" in m for m in msgs), msgs


def test_legend_includegraphics_between_subfloats_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_STAR_OPEN
        + "    \\centering\n"
        + "    \\subfloat[A]{\\includegraphics{a.png}}\n"
        + "    \\subfloat[B]{\\includegraphics{b.png}}\\\\\n"
        + "    \\includegraphics[width=2.5cm]{legend.png}\\\\\n"
        + "    \\caption{Caption.}\n"
        + FIG_STAR_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not caplog.records


def test_reports_correct_line_number(tmp_path, caplog):
    tex = _write(tmp_path, (
        "% line 1\n"
        "% line 2\n"
        + FIG_STAR_OPEN  # line 3
        + "    \\centering\n"  # line 4
        + "    \\textbf{Heading}\\\\\n"  # line 5
        + "    \\caption{Caption.}\n"
        + FIG_STAR_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert any(":5" in r.message for r in caplog.records), [r.message for r in caplog.records]


def test_input_files_scanned(tmp_path, caplog):
    main = tmp_path / "main.tex"
    body = tmp_path / "body.tex"
    main.write_text(r"\input{body}")
    body.write_text(
        FIG_STAR_OPEN
        + "    \\textbf{Heading}\\\\\n"
        + "    \\caption{Caption.}\n"
        + FIG_STAR_CLOSE
    )
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(main)
    assert any("body.tex" in r.message for r in caplog.records)


def test_commented_out_textbf_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, (
        FIG_OPEN
        + "    \\centering\n"
        + "    % \\textbf{old heading - removed}\n"
        + "    \\includegraphics{a.png}\n"
        + "    \\caption{Caption.}\n"
        + FIG_CLOSE
    ))
    with caplog.at_level("WARNING"):
        _warn_text_in_figure(tex)
    assert not caplog.records
