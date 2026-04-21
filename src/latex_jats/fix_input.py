"""Fix common LaTeX source issues that break or degrade the JATS conversion.

Usage:
    uv run fix-input path/to/main.tex          # preview changes (dry-run)
    uv run fix-input path/to/main.tex --apply   # apply changes in-place

Fixes applied:
  - bare < and > in text mode  → wrapped in math mode ($<$, $>$)
  - trailing punctuation after \\includegraphics → removed
  - \\title{} inside table environments → \\caption{}
  - unescaped & in .bib field values → escaped as \\&
"""

import argparse
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _collect_tex_files(main_tex: Path) -> list[Path]:
    """Return main_tex plus all \\input / \\include targets and .bib files."""
    tex_dir = main_tex.parent
    files = [main_tex]
    try:
        text = main_tex.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = main_tex.read_text(encoding="latin-1")
    for m in re.finditer(r'\\(?:input|include)\{([^}]+)\}', text):
        child = tex_dir / m.group(1)
        if not child.suffix:
            child = child.with_suffix('.tex')
        if child.exists() and child not in files:
            files.append(child)
    # Also collect .bib files referenced via \addbibresource or \bibliography
    for m in re.finditer(r'\\(?:addbibresource|bibliography)\{([^}]+)\}', text):
        for name in m.group(1).split(','):
            child = tex_dir / name.strip()
            if not child.suffix:
                child = child.with_suffix('.bib')
            if child.exists() and child not in files:
                files.append(child)
    return files


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1").splitlines(keepends=True)


def fix_bare_angle_brackets(lines: list[str], filename: str) -> list[str]:
    r"""Replace bare < and > in text mode with $<$ and $>$.

    Skips math environments, inline math, comments, tabularx column specs
    (lines containing \begin{tabularx} or >{\...}), and \makeatletter blocks
    (where < and > are typically operators in \ifdim/\ifnum or catcode-altered
    internals, not text to render).
    """
    out = []
    in_math_env = False
    in_verbatim_env = False
    in_makeat = False
    for lineno, line in enumerate(lines, 1):
        stripped = re.sub(r'(?<!\\)%.*', '', line)

        if re.search(r'\\begin\{(equation|align|math|displaymath|eqnarray)', stripped):
            in_math_env = True
        if re.search(r'\\end\{(equation|align|math|displaymath|eqnarray)', stripped):
            in_math_env = False

        if re.search(r'\\begin\{(lstlisting|minted|verbatim)', stripped):
            in_verbatim_env = True
        if re.search(r'\\end\{(lstlisting|minted|verbatim)', stripped):
            in_verbatim_env = False
            out.append(line)
            continue

        if r'\makeatletter' in stripped:
            in_makeat = True
        if r'\makeatother' in stripped:
            in_makeat = False
            out.append(line)
            continue

        if in_math_env or in_verbatim_env or in_makeat:
            out.append(line)
            continue

        # skip tabularx column specs like >{...} or p{...}>{...}
        if re.search(r'>\s*\{\\', stripped):
            out.append(line)
            continue

        # check if text-mode bare < or > exist (outside inline math)
        text_only = re.sub(r'\$[^$]*\$', '', stripped)
        if not re.search(r'[<>]', text_only):
            out.append(line)
            continue

        # replace bare < > with $<$ $>$, but not inside inline math or comments
        def _replace_in_text(line_text: str) -> str:
            # split line into: inline-math segments, comment, and text
            parts = []
            pos = 0
            # find inline math spans and comment
            for m in re.finditer(r'\$[^$]*\$|(?<!\\)%.*', line_text):
                if m.start() > pos:
                    parts.append(('text', line_text[pos:m.start()]))
                parts.append(('skip', m.group()))
                pos = m.end()
            if pos < len(line_text):
                parts.append(('text', line_text[pos:]))

            result = []
            for kind, segment in parts:
                if kind == 'text':
                    segment = segment.replace('>', '$>$').replace('<', '$<$')
                result.append(segment)
            return ''.join(result)

        new_line = _replace_in_text(line)
        if new_line != line:
            logger.info("FIXED bare </>: %s:%d", filename, lineno)
        out.append(new_line)

    return out


def fix_stray_after_includegraphics(lines: list[str], filename: str) -> list[str]:
    r"""Remove trailing punctuation after \includegraphics{...}."""
    pattern = re.compile(r'(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})\s*([.,;:!?]+)')
    out = []
    for lineno, line in enumerate(lines, 1):
        new_line = pattern.sub(r'\1', line)
        if new_line != line:
            logger.info(r"FIXED stray text after \includegraphics: %s:%d", filename, lineno)
        out.append(new_line)
    return out


# Unicode characters that break pdflatex, mapped to (replacement, description).
# NB: smart quotes, en/em dashes, etc. are handled fine by inputenc and are NOT
# included here — only characters that actually cause compilation failures.
UNICODE_BREAKERS: dict[str, tuple[str, str]] = {
    '\u2212': ('-', 'MINUS SIGN'),
}


def fix_unicode_text_chars(lines: list[str], filename: str) -> list[str]:
    """Replace Unicode characters that break pdflatex with ASCII equivalents."""
    out = []
    for lineno, line in enumerate(lines, 1):
        new_line = line
        for char, (replacement, desc) in UNICODE_BREAKERS.items():
            if char in new_line:
                new_line = new_line.replace(char, replacement)
                logger.info(
                    "FIXED Unicode %s (U+%04X): %s:%d",
                    desc, ord(char), filename, lineno,
                )
        out.append(new_line)
    return out


# Map minted language names to listings language names where they differ.
# Languages not listed here are passed through as-is (listings handles many
# language names identically to Pygments/minted).
_MINTED_TO_LISTINGS_LANG: dict[str, str] = {
    "pycon": "Python",
    "python3": "Python",
    "js": "Java",  # listings has no JS — Java is a rough fallback
}


def fix_minted_to_listings(lines: list[str], filename: str) -> list[str]:
    r"""Replace minted environments and package with listings equivalents.

    Converts \usepackage{minted} → \usepackage{listings}, removes
    \usemintedstyle{...}, and converts \begin{minted}[opts]{lang} →
    \begin{lstlisting}[language=Lang].
    """
    out = []
    for lineno, line in enumerate(lines, 1):
        # \usepackage{minted} → \usepackage{listings}
        if re.match(r'\s*\\usepackage\{minted\}', line):
            new_line = re.sub(r'\\usepackage\{minted\}', r'\\usepackage{listings}', line)
            logger.info("FIXED minted→listings (usepackage): %s:%d", filename, lineno)
            out.append(new_line)
            continue

        # Remove \usemintedstyle{...} lines entirely
        if re.match(r'\s*\\usemintedstyle\{', line):
            logger.info("FIXED minted→listings (remove usemintedstyle): %s:%d", filename, lineno)
            continue

        # \begin{minted}[opts]{lang} → \begin{lstlisting}[language=Lang]
        m = re.match(r'(\s*)\\begin\{minted\}(?:\[[^\]]*\])?\{(\w+)\}(.*)', line)
        if m:
            indent, lang, rest = m.groups()
            lang_listings = _MINTED_TO_LISTINGS_LANG.get(lang, lang.capitalize() if lang.islower() else lang)
            new_line = f"{indent}\\begin{{lstlisting}}[language={lang_listings}]{rest}\n"
            logger.info("FIXED minted→listings (begin): %s:%d", filename, lineno)
            out.append(new_line)
            continue

        # \end{minted} → \end{lstlisting}
        if re.match(r'\s*\\end\{minted\}', line):
            new_line = re.sub(r'\\end\{minted\}', r'\\end{lstlisting}', line)
            logger.info("FIXED minted→listings (end): %s:%d", filename, lineno)
            out.append(new_line)
            continue

        out.append(line)
    return out


def fix_title_in_table(lines: list[str], filename: str) -> list[str]:
    r"""Replace \title{} with \caption{} inside table environments."""
    out = []
    in_table = False
    for lineno, line in enumerate(lines, 1):
        stripped = re.sub(r'(?<!\\)%.*', '', line)
        if re.search(r'\\begin\{table\}', stripped):
            in_table = True
        if re.search(r'\\end\{table\}', stripped):
            in_table = False
        if in_table and re.search(r'\\title\{', stripped):
            new_line = re.sub(r'\\title\{', r'\\caption{', line)
            logger.info(r"FIXED \title{} → \caption{} in table: %s:%d", filename, lineno)
            out.append(new_line)
        else:
            out.append(line)
    return out


def fix_ampersand_in_metadata(lines: list[str], filename: str) -> list[str]:
    r"""Escape bare & in \authorsnames, \authorsaffiliations, \shortauthors.

    These macros contain text, never alignment tabs. A bare & causes LaTeXML
    to error with "T_ALIGN[&] should never reach Stomach!".
    """
    text = ''.join(lines)
    changed = False
    for macro in ('authorsnames', 'authorsaffiliations', 'shortauthors'):
        for m in re.finditer(rf'\\{macro}\{{', text):
            start = m.end()
            depth = 1
            pos = start
            while pos < len(text) and depth > 0:
                if text[pos] == '{':
                    depth += 1
                elif text[pos] == '}':
                    depth -= 1
                pos += 1
            body = text[start:pos - 1]
            fixed_body = re.sub(r'(?<!\\)&', r'\\&', body)
            if fixed_body != body:
                text = text[:start] + fixed_body + text[pos - 1:]
                lineno = text[:m.start()].count('\n') + 1
                logger.info(r"FIXED bare & in \%s: %s:%d", macro, filename, lineno)
                changed = True
    if changed:
        return text.splitlines(keepends=True)
    return lines


ALL_FIXES = [
    fix_minted_to_listings,
    fix_bare_angle_brackets,
    fix_stray_after_includegraphics,
    fix_unicode_text_chars,
    fix_title_in_table,
    fix_ampersand_in_metadata,
]


def fix_bib_ampersands(lines: list[str], filename: str) -> list[str]:
    r"""Escape unescaped & in .bib field values.

    Replaces bare & with \& inside braced field values like
    journal = {Memory & Cognition}. Leaves already-escaped \& alone.
    """
    out = []
    for lineno, line in enumerate(lines, 1):
        # Only fix lines that look like bib field values: key = {... & ...}
        # and that contain an unescaped & (not preceded by \)
        if re.search(r'(?<!\\)&', line) and re.search(r'=\s*\{', line):
            new_line = re.sub(r'(?<!\\)&', r'\\&', line)
            if new_line != line:
                logger.info("FIXED unescaped &: %s:%d", filename, lineno)
            out.append(new_line)
        else:
            out.append(line)
    return out


def fix_bib_dotless_i_accent(lines: list[str], filename: str) -> list[str]:
    r"""Replace {\'\i} with {\'i} in .bib files.

    The LaTeX {\'\i} (accent on dotless-i) is technically correct, but bibtex
    expands it to decomposed Unicode (U+0131 + U+0301) that pdflatex cannot
    handle. Using {\'i} instead produces the same visual output and avoids
    the problem.
    """
    out = []
    for lineno, line in enumerate(lines, 1):
        new_line = line.replace(r"{\'\i}", r"{\'i}")
        # Also handle the form without outer braces: \'\i → \'i
        new_line = new_line.replace(r"\'\i", r"\'i")
        if new_line != line:
            logger.info(
                r"FIXED {\'\i} → {\'i} (avoids bibtex decomposed Unicode): %s:%d",
                filename, lineno,
            )
        out.append(new_line)
    return out


BIB_FIXES = [
    fix_bib_ampersands,
    fix_bib_dotless_i_accent,
]


def fix_file(path: Path, apply: bool) -> int:
    """Run all fixes on a single file. Returns number of lines changed."""
    lines = _read_lines(path)
    fixes = BIB_FIXES if path.suffix == '.bib' else ALL_FIXES
    result = lines
    for fix in fixes:
        result = fix(result, path.name)

    changed = sum(1 for a, b in zip(lines, result) if a != b)
    if changed and apply:
        path.write_text(''.join(result), encoding="utf-8")
    return changed


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Fix common LaTeX source issues for JATS conversion."
    )
    parser.add_argument("input", help="Main .tex file")
    parser.add_argument("--apply", action="store_true",
                        help="Apply fixes in-place (default: dry-run)")
    args = parser.parse_args()

    input_path = Path(args.input)
    files = _collect_tex_files(input_path)

    total = 0
    for f in files:
        n = fix_file(f, apply=args.apply)
        total += n

    if total == 0:
        logger.info("No issues found.")
    elif args.apply:
        logger.info("Fixed %d line(s) across %d file(s).", total, len(files))
    else:
        logger.info("Found %d line(s) to fix across %d file(s). "
                     "Run with --apply to apply.", total, len(files))


if __name__ == "__main__":
    main()
