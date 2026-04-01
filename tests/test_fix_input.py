from latex_jats.fix_input import fix_bare_angle_brackets, fix_stray_after_includegraphics


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
