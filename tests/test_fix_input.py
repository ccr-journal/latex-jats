from latex_jats.fix_input import (
    fix_bare_angle_brackets,
    fix_bib_dotless_i_accent,
    fix_stray_after_includegraphics,
    fix_title_in_table,
    fix_unicode_text_chars,
)


class TestFixBareAngleBrackets:
    def test_bare_greater_than(self):
        lines = ["accuracy > baseline and < threshold\n"]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == ["accuracy $>$ baseline and $<$ threshold\n"]

    def test_inside_inline_math_unchanged(self):
        lines = ["where $x > 0$ holds\n"]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == lines

    def test_inside_math_env_unchanged(self):
        lines = [
            "\\begin{equation}\n",
            "x > 0\n",
            "\\end{equation}\n",
        ]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == lines

    def test_tabularx_column_spec_unchanged(self):
        lines = ["\\newcolumntype{Y}{>{\\RaggedRight}X}\n"]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == lines

    def test_comment_unchanged(self):
        lines = ["text % x > 0\n"]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == lines

    def test_no_angle_brackets_unchanged(self):
        lines = ["normal text here\n"]
        result = fix_bare_angle_brackets(lines, "test.tex")
        assert result == lines


class TestFixStrayAfterIncludegraphics:
    def test_trailing_period(self):
        lines = ["    \\includegraphics[width=0.8\\textwidth]{img.png}.\n"]
        result = fix_stray_after_includegraphics(lines, "test.tex")
        assert result == ["    \\includegraphics[width=0.8\\textwidth]{img.png}\n"]

    def test_trailing_comma(self):
        lines = ["\\includegraphics{img.png},\n"]
        result = fix_stray_after_includegraphics(lines, "test.tex")
        assert result == ["\\includegraphics{img.png}\n"]

    def test_no_trailing_punct_unchanged(self):
        lines = ["\\includegraphics{img.png}\n"]
        result = fix_stray_after_includegraphics(lines, "test.tex")
        assert result == lines

    def test_no_options(self):
        lines = ["\\includegraphics{img.png}.\n"]
        result = fix_stray_after_includegraphics(lines, "test.tex")
        assert result == ["\\includegraphics{img.png}\n"]


class TestFixUnicodeTextChars:
    def test_replaces_unicode_minus(self):
        lines = ["value = \u22120.041\n"]
        result = fix_unicode_text_chars(lines, "test.tex")
        assert result == ["value = -0.041\n"]

    def test_no_unicode_unchanged(self):
        lines = ["value = -0.041\n"]
        result = fix_unicode_text_chars(lines, "test.tex")
        assert result == lines

    def test_multiple_on_same_line(self):
        lines = ["\u22120.5 to \u22121.0\n"]
        result = fix_unicode_text_chars(lines, "test.tex")
        assert result == ["-0.5 to -1.0\n"]


class TestFixTitleInTable:
    def test_title_replaced_inside_table(self):
        lines = [
            "\\begin{table}\n",
            "\\title{My table}\n",
            "\\end{table}\n",
        ]
        result = fix_title_in_table(lines, "test.tex")
        assert result == [
            "\\begin{table}\n",
            "\\caption{My table}\n",
            "\\end{table}\n",
        ]

    def test_title_outside_table_unchanged(self):
        lines = ["\\title{Document Title}\n"]
        result = fix_title_in_table(lines, "test.tex")
        assert result == lines

    def test_title_after_end_table_unchanged(self):
        lines = [
            "\\begin{table}\n",
            "\\end{table}\n",
            "\\title{Not in table}\n",
        ]
        result = fix_title_in_table(lines, "test.tex")
        assert result == lines


class TestFixBibDotlessIAccent:
    def test_replaces_braced_form(self):
        lines = [r"  author={Mach{\'\i}o-Regidor, Francisco}," + "\n"]
        result = fix_bib_dotless_i_accent(lines, "test.bib")
        assert result == [r"  author={Mach{\'i}o-Regidor, Francisco}," + "\n"]

    def test_no_dotless_i_unchanged(self):
        lines = [r"  author={Garc{\'i}a, Juan}," + "\n"]
        result = fix_bib_dotless_i_accent(lines, "test.bib")
        assert result == lines
