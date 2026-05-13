"""Unit tests for the structured-affiliation post-processor and its parser."""

import xml.etree.ElementTree as ET

from jatsmith.convert import _parse_addaffiliations, structure_affiliations


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- _parse_addaffiliations ---------------------------------------------------


def test_parse_simple(tmp_path):
    tex = _write(tmp_path, "main.tex",
                 r"\addaffiliation{aff-1}{University of X}{NL}" "\n")
    assert _parse_addaffiliations(tex) == {
        "aff-1": {"dept": "", "org": "University of X", "cc": "NL"},
    }


def test_parse_with_department(tmp_path):
    tex = _write(tmp_path, "main.tex",
                 r"\addaffiliation{u}[Department of Y]{Uni X}{US}" "\n")
    assert _parse_addaffiliations(tex) == {
        "u": {"dept": "Department of Y", "org": "Uni X", "cc": "US"},
    }


def test_parse_lowercases_to_uppercase(tmp_path):
    tex = _write(tmp_path, "main.tex",
                 r"\addaffiliation{u}{Uni X}{nl}" "\n")
    assert _parse_addaffiliations(tex)["u"]["cc"] == "NL"


def test_parse_multiline_args(tmp_path):
    tex = _write(tmp_path, "main.tex",
                 "\\addaffiliation{u}{Department of X,\nUniversity of Y}{DE}\n")
    info = _parse_addaffiliations(tex)["u"]
    assert info["org"] == "Department of X, University of Y"
    assert info["cc"] == "DE"


def test_parse_follows_input(tmp_path):
    _write(tmp_path, "frontmatter.tex",
           r"\addaffiliation{u}{Uni X}{NL}" "\n")
    main = _write(tmp_path, "main.tex",
                  r"\input{frontmatter}" "\n")
    assert _parse_addaffiliations(main) == {
        "u": {"dept": "", "org": "Uni X", "cc": "NL"},
    }


def test_parse_no_addaffiliation_returns_empty(tmp_path):
    tex = _write(tmp_path, "main.tex",
                 r"\authorsaffiliations{Uni X, Uni Y}" "\n")
    assert _parse_addaffiliations(tex) == {}


def test_parse_strips_latex_escapes(tmp_path):
    r"""\& / \% / \_ etc. are rendered as bare & / % / _ in JATS text content,
    so the parser must normalise the same way for the lookup key to match."""
    tex = _write(tmp_path, "main.tex",
                 r"\addaffiliation{u}[R\&D Group]"
                 r"{Wageningen University \& Research}{NL}" "\n")
    info = _parse_addaffiliations(tex)["u"]
    assert info["dept"] == "R&D Group"
    assert info["org"] == "Wageningen University & Research"


def test_structure_matches_aff_with_ampersand(tmp_path):
    r"""End-to-end: source has \&, JATS text has &, the rewriter still
    finds and structures the aff (SCHR regression)."""
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{w}[Strategic Communication Group]"
        r"{Wageningen University \& Research}{NL}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><aff>Strategic Communication Group, '
        'Wageningen University &amp; Research, NL</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    assert aff.find("institution-wrap/institution").text == \
        "Wageningen University & Research"
    assert aff.find("institution[@content-type='department']").text == \
        "Strategic Communication Group"


def test_parse_skips_malformed(tmp_path):
    """A truncated \\addaffiliation call shouldn't crash the parser."""
    tex = _write(tmp_path, "main.tex",
                 r"\addaffiliation{u}{Uni X}" "\n"           # 3-arg form, no CC
                 r"\addaffiliation{v}{Uni Y}{NL}" "\n")      # well-formed
    info = _parse_addaffiliations(tex)
    # u is missing the country brace → cc is empty
    assert info["u"]["cc"] == ""
    assert info["v"] == {"dept": "", "org": "Uni Y", "cc": "NL"}


# --- structure_affiliations ---------------------------------------------------


def _setup(tmp_path, tex_body, jats_body):
    tex = _write(tmp_path, "main.tex", tex_body)
    jats = _write(tmp_path, "out.xml", jats_body)
    return tex, jats


def test_structure_replaces_flat_aff_with_full_shape(tmp_path):
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{u}[Communication Science]{University of Amsterdam}{NL}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><name><surname>Doe</surname></name>'
        '<aff>Communication Science, University of Amsterdam, NL</aff>'
        '</contrib></contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    assert aff.find("institution[@content-type='department']").text == "Communication Science"
    assert aff.find("institution-wrap/institution").text == "University of Amsterdam"
    country = aff.find("country")
    assert country.text == "NL" and country.get("country") == "NL"
    # Text content cleared between elements.
    assert (aff.text or "").strip() == ""


def test_structure_skips_department_when_blank(tmp_path):
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{u}{Vrije Universiteit Amsterdam}{NL}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><aff>Vrije Universiteit Amsterdam, NL</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    assert aff.find("institution[@content-type='department']") is None
    assert aff.find("institution-wrap/institution").text == "Vrije Universiteit Amsterdam"
    assert aff.find("country").text == "NL"


def test_structure_handles_whitespace_in_flat_blob(tmp_path):
    """LaTeXML may inject whitespace/newlines into the inline aff text."""
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{u}{University of X}{DE}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><aff>University of X,\n  DE</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    assert aff.find("institution-wrap/institution").text == "University of X"


def test_structure_noop_when_no_addaffiliation(tmp_path):
    """Legacy \\authorsaffiliations sources don't trigger restructuring."""
    tex, jats = _setup(tmp_path,
        r"\authorsaffiliations{Uni X}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><aff>Uni X</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    # Untouched: still flat text, no <institution> children.
    assert aff.text == "Uni X"
    assert aff.find("institution") is None


def test_structure_leaves_unmatched_aff_alone(tmp_path):
    """If an <aff>'s text doesn't match any \\addaffiliation entry, skip it."""
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{u}{University of X}{DE}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><aff>Some other institution</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    aff = ET.parse(jats).getroot().find(".//aff")
    assert aff.text == "Some other institution"
    assert aff.find("institution") is None


def test_structure_idempotent_on_duplicate_affs(tmp_path):
    """Two contribs sharing the same affiliation both get structured."""
    tex, jats = _setup(tmp_path,
        r"\addaffiliation{u}{University of X}{NL}" "\n",
        '<article><article-meta><contrib-group>'
        '<contrib><name><surname>A</surname></name>'
        '<aff>University of X, NL</aff></contrib>'
        '<contrib><name><surname>B</surname></name>'
        '<aff>University of X, NL</aff></contrib>'
        '</contrib-group></article-meta></article>',
    )
    structure_affiliations(str(jats), str(tex))
    affs = ET.parse(jats).getroot().findall(".//aff")
    assert len(affs) == 2
    for aff in affs:
        assert aff.find("institution-wrap/institution").text == "University of X"
        assert aff.find("country").text == "NL"
