import logging

from jatsmith.convert import _warn_linebreak_in_multirow


def _write(tmp_path, body):
    p = tmp_path / "main.tex"
    p.write_text(body, encoding="utf-8")
    return p


def test_bare_linebreak_warns(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\begin{tabular}{ll}
1 & \multirow{2}{*}{Static\\Visual} \\
2 & x \\
\end{tabular}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1
    assert "main.tex:3" in caplog.records[0].message
    assert r"\shortstack" in caplog.records[0].message
    # We deliberately don't suggest \makecell — its JATS output is a
    # nested table inside the cell, which Ingenta may not render cleanly.
    assert r"\makecell" not in caplog.records[0].message


def test_shortstack_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow{2}{*}{\shortstack{Static\\Visual}}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert caplog.records == []


def test_makecell_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow{2}{*}{\makecell{Static\\Visual}}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert caplog.records == []


def test_multirow_without_linebreak_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow{2}{*}{Visual}
\multirow{4}{=}{Audio}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert caplog.records == []


def test_starred_form_warns(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow*{2}{*}{Static\\Visual}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1


def test_optional_vpos_arg_warns(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow[t]{2}{*}{Static\\Visual}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1


def test_multiline_call_detected(tmp_path, caplog):
    # XUE-shaped: \multirow spans two lines in source.
    tex = _write(tmp_path, """
1 & \\multirow{4}{=}{\\centering Static\\\\Visual}
  & Brightness \\\\
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1
    # The \multirow is on line 2.
    assert "main.tex:2" in caplog.records[0].message


def test_tabularnewline_also_warns(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow{2}{*}{Static\tabularnewline Visual}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1


def test_commented_multirow_does_not_warn(tmp_path, caplog):
    tex = _write(tmp_path, r"""
% \multirow{2}{*}{Static\\Visual}
\multirow{2}{*}{Plain}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert caplog.records == []


def test_mixed_good_and_bad_only_bad_warns(tmp_path, caplog):
    tex = _write(tmp_path, r"""
\multirow{2}{*}{\shortstack{Good\\OK}}
\multirow{2}{*}{Bad\\Cell}
\multirow{4}{=}{Plain}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert len(caplog.records) == 1
    assert "main.tex:3" in caplog.records[0].message


def test_input_file_is_scanned(tmp_path, caplog):
    (tmp_path / "body.tex").write_text(
        r"\multirow{2}{*}{Static\\Visual}" + "\n", encoding="utf-8"
    )
    main = _write(tmp_path, "\\input{body}\n")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(main)
    assert len(caplog.records) == 1
    assert "body.tex" in caplog.records[0].message


def test_multirowsetup_is_not_matched(tmp_path, caplog):
    # \multirowsetup is a different control sequence; word-boundary
    # in the regex should keep us from matching it.
    tex = _write(tmp_path, r"""
\renewcommand{\multirowsetup}{\centering}
""")
    with caplog.at_level(logging.WARNING):
        _warn_linebreak_in_multirow(tex)
    assert caplog.records == []
