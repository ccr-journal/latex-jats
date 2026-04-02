"""Fix common LaTeX source issues that break or degrade the JATS conversion.

Usage:
    uv run fix-input path/to/main.tex          # preview changes (dry-run)
    uv run fix-input path/to/main.tex --apply   # apply changes in-place

Fixes applied:
  - bare < and > in text mode  → wrapped in math mode ($<$, $>$)
  - trailing punctuation after \\includegraphics → removed
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

    Skips math environments, inline math, comments, and tabularx column
    specs (lines containing \begin{tabularx} or >{\...}).
    """
    out = []
    in_math_env = False
    for lineno, line in enumerate(lines, 1):
        stripped = re.sub(r'(?<!\\)%.*', '', line)

        if re.search(r'\\begin\{(equation|align|math|displaymath|eqnarray)', stripped):
            in_math_env = True
        if re.search(r'\\end\{(equation|align|math|displaymath|eqnarray)', stripped):
            in_math_env = False

        if in_math_env:
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
            logger.info("fix bare </>: %s:%d", filename, lineno)
        out.append(new_line)

    return out


def fix_stray_after_includegraphics(lines: list[str], filename: str) -> list[str]:
    r"""Remove trailing punctuation after \includegraphics{...}."""
    pattern = re.compile(r'(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})\s*([.,;:!?]+)')
    out = []
    for lineno, line in enumerate(lines, 1):
        new_line = pattern.sub(r'\1', line)
        if new_line != line:
            logger.info(r"fix stray text after \includegraphics: %s:%d", filename, lineno)
        out.append(new_line)
    return out


ALL_FIXES = [
    fix_bare_angle_brackets,
    fix_stray_after_includegraphics,
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
                logger.info("fix unescaped &: %s:%d", filename, lineno)
            out.append(new_line)
        else:
            out.append(line)
    return out


BIB_FIXES = [
    fix_bib_ampersands,
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
