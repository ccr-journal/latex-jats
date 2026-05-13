import logging

from jatsmith.convert import _warn_missing_affiliation_country


def _write(tmp_path, body):
    p = tmp_path / "main.tex"
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_country_codes_no_warning(tmp_path, caplog):
    tex = (
        r"\addaffiliation{aff-1}{University of Amsterdam}{NL}" "\n"
        r"\addaffiliation{aff-2}[Department of X]{University of Y}{US}" "\n"
    )
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert caplog.records == []


def test_empty_country_code_warns(tmp_path, caplog):
    # The URMA failure mode: country slot present but empty.
    tex = (
        r"\addaffiliation{aff-1}{Department of Informatics, "
        r"University of Zurich, Zurich, Switzerland}{}" "\n"
    )
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert len(caplog.records) == 1
    msg = caplog.records[0].message
    assert "aff-1" in msg
    assert "main.tex:1" in msg
    assert "empty country code" in msg


def test_country_name_warns(tmp_path, caplog):
    tex = r"\addaffiliation{aff-1}{University of X}{Switzerland}" "\n"
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert len(caplog.records) == 1
    msg = caplog.records[0].message
    assert "Switzerland" in msg
    assert "invalid country code" in msg


def test_missing_country_arg_warns(tmp_path, caplog):
    # Only label + org provided — no country argument at all.
    tex = r"\addaffiliation{aff-1}{University of X}" "\n"
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert len(caplog.records) == 1
    assert "missing the ISO country code" in caplog.records[0].message


def test_country_code_is_case_insensitive(tmp_path, caplog):
    tex = r"\addaffiliation{aff-1}{University of X}{nl}" "\n"
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert caplog.records == []


def test_optional_department_handled(tmp_path, caplog):
    tex = r"\addaffiliation{aff-1}[Communication Science]{UvA}{NL}" "\n"
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert caplog.records == []


def test_multiline_arg(tmp_path, caplog):
    tex = (
        "\\addaffiliation{aff-1}{Department of Informatics, University\n"
        "of Zurich, Zurich, Switzerland}{}\n"
    )
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert len(caplog.records) == 1
    assert "aff-1" in caplog.records[0].message


def test_legacy_authorsaffiliations_not_flagged(tmp_path, caplog):
    tex = r"\authorsaffiliations{University of X; University of Y}" "\n"
    path = _write(tmp_path, tex)
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(path)
    assert caplog.records == []


def test_follows_input(tmp_path, caplog):
    child = tmp_path / "frontmatter.tex"
    child.write_text(
        r"\addaffiliation{aff-1}{University of X}{}" "\n",
        encoding="utf-8",
    )
    main = _write(tmp_path, r"\input{frontmatter}" "\n")
    with caplog.at_level(logging.WARNING):
        _warn_missing_affiliation_country(main)
    assert len(caplog.records) == 1
    assert "frontmatter.tex" in caplog.records[0].message
