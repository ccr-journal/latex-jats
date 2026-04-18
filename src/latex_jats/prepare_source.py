"""Validate and prepare a LaTeX source directory for JATS conversion.

Checks that the source folder is well-formed, optionally applies source fixes,
and compiles the LaTeX document (pdflatex + biber/bibtex) to produce:
  - main.pdf  — for the web preview
  - main.bbl  — required by the JATS converter

Usage:
    uv run prepare-source path/to/latex/          # validate + compile if needed
    uv run prepare-source path/to/main.tex        # same, accepts file too
    uv run prepare-source path/to/latex/ --fix-simple-problems
    uv run prepare-source path/to/latex/ --force
"""

import argparse
import logging
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from latex_jats.ccr_cls import warn_if_outdated as _warn_if_ccr_cls_outdated
from latex_jats.fix_input import _collect_tex_files, fix_file

logger = logging.getLogger(__name__)


def _find_main_tex(source: Path) -> Path:
    """Return the main.tex path given either a directory or a .tex file."""
    if source.is_file():
        return source
    candidate = source / "main.tex"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"No main.tex found in {source}")


def _needs_compilation(latex_dir: Path) -> bool:
    """Return True if main.pdf or main.bbl are missing or stale."""
    pdf = latex_dir / "main.pdf"
    bbl = latex_dir / "main.bbl"
    if not pdf.exists() or not bbl.exists():
        return True
    # Recompile if any .tex or .bib file is newer than main.pdf/main.bbl
    oldest_output = min(pdf.stat().st_mtime, bbl.stat().st_mtime)
    source_files = (list(latex_dir.glob("*.tex")) + list(latex_dir.glob("**/*.tex"))
                    + list(latex_dir.glob("*.bib")))
    return any(f.stat().st_mtime > oldest_output for f in source_files)


def _run(cmd: list[str], cwd: Path, log_file: Path | None = None) -> bool:
    """Run a command, streaming output (or capturing to log_file). Returns True on success."""
    logger.info("Running: %s", " ".join(cmd))
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("wb") as fh:
            result = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        logger.error("Command failed (exit %d): %s", result.returncode, " ".join(cmd))
        return False
    return True


def validate_structure(latex_dir: Path) -> list[str]:
    """Check for common structural issues. Returns a list of warning strings."""
    warnings = []
    if not (latex_dir / "main.tex").exists():
        warnings.append("main.tex not found")
    preamble = (latex_dir / "main.tex").read_text(encoding="utf-8", errors="replace")
    if r"\doi{" not in preamble:
        warnings.append(r"No \doi{} macro found in main.tex")
    return warnings


def _normalize_bbl(latex_dir: Path) -> None:
    """Apply Unicode NFC normalization to main.bbl if it exists.

    Bibtex/biber can emit decomposed Unicode (e.g. combining accents) that
    pdflatex cannot handle. NFC normalization recombines decomposed sequences
    into their precomposed equivalents. Any remaining combining marks that
    NFC cannot resolve are warned about.
    """
    bbl = latex_dir / "main.bbl"
    if not bbl.exists():
        return
    text = bbl.read_text(encoding="utf-8")
    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        bbl.write_text(normalized, encoding="utf-8")
        logger.info("Normalized main.bbl to Unicode NFC (fixed combining characters)")
    # Warn about any remaining combining marks that NFC couldn't resolve
    for lineno, line in enumerate(normalized.splitlines(), 1):
        for ch in line:
            if unicodedata.category(ch).startswith("M"):
                logger.warning(
                    "main.bbl:%d: remaining combining mark U+%04X (%s) after "
                    "NFC normalization — this will likely break pdflatex. "
                    "Fix the .bib source entry manually.",
                    lineno, ord(ch), unicodedata.name(ch, "UNKNOWN"),
                )


def _patch_ccr_cls(workspace_dir: Path, engine: str = "pdflatex"):
    """Patch ccr.cls in the workspace: add \\pdfminorversion=7, drop pstricks."""
    cls = workspace_dir / "ccr.cls"
    if not cls.exists():
        return
    text = cls.read_text()
    changed = False
    # Add \pdfminorversion=7 early so pdflatex produces PDF 1.7
    # (xelatex/lualatex handle any PDF version natively)
    if engine == "pdflatex" and r'\pdfminorversion' not in text:
        text = r'\pdfminorversion=7' + '\n' + text
        changed = True
    elif engine != "pdflatex" and r'\pdfminorversion' in text:
        text = re.sub(r'\\pdfminorversion\s*=\s*\d+\s*\n?', '', text)
        changed = True
    # pstricks is unused and can conflict with pdflatex
    if r'\RequirePackage{pstricks}' in text:
        text = text.replace(r'\RequirePackage{pstricks}', '% \\RequirePackage{pstricks}  % removed: unused, conflicts with pdflatex')
        changed = True
    if changed:
        cls.write_text(text)
        logger.info("Patched ccr.cls (pdfminorversion, pstricks)")


def prepare_workspace(source_dir: Path, workspace_dir: Path,
                      fix_problems: bool = False) -> Path:
    """Create a workspace copy of the source and apply fixes + warnings.

    Copies the source tree into workspace_dir, optionally applies fix_input
    fixes, and runs all source-quality warnings on the result.

    Returns the path to main.tex in the workspace.
    """
    from latex_jats.convert import warn_source_issues

    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(source_dir, workspace_dir)
    main_tex = workspace_dir / "main.tex"

    engine = _detect_tex_engine(main_tex)
    _patch_ccr_cls(workspace_dir, engine)
    _warn_if_ccr_cls_outdated(workspace_dir)

    # Apply fixes to the workspace copy (if requested)
    if fix_problems:
        logger.info("Applying source fixes (--fix-simple-problems)...")
        fixed = 0
        for tex_file in _collect_tex_files(main_tex):
            fixed += fix_file(tex_file, apply=True)
        if fixed:
            logger.info("Fixed %d line(s).", fixed)
        else:
            logger.info("No source fixes needed.")

    # Warn about source issues (on the post-fix workspace)
    warn_source_issues(main_tex)

    return main_tex


def _detect_tex_engine(main_tex: Path) -> str:
    """Detect the TeX engine from a ``% !TeX program = ...`` magic comment.

    Scans the first 10 lines of the file.  Returns ``"xelatex"``,
    ``"lualatex"``, or ``"pdflatex"`` (the default).
    """
    with open(main_tex) as f:
        for _, line in zip(range(10), f):
            m = re.match(r"^\s*%\s*!TeX\s+program\s*=\s*(\S+)", line, re.IGNORECASE)
            if m:
                engine = m.group(1).lower()
                if engine in ("xelatex", "lualatex", "pdflatex"):
                    return engine
                logger.warning("Unknown TeX engine %r in magic comment — using pdflatex", engine)
                return "pdflatex"
    return "pdflatex"


def compile_latex(latex_dir: Path, log_dir: Path | None = None) -> bool:
    """Run latex → biber/bibtex → latex → latex.

    The LaTeX engine is determined by a ``% !TeX program = xelatex`` magic
    comment in ``main.tex`` (first 10 lines); defaults to pdflatex.

    Detects biber vs bibtex by checking for main.bcf after the first
    run (biblatex writes a .bcf control file; plain bibtex does not).

    If log_dir is given, stdout/stderr of each step is captured there and
    the engine's main.log / biber's main.blg are also copied in.

    Returns True if compilation succeeded.
    """
    engine = _detect_tex_engine(latex_dir / "main.tex")
    if engine != "pdflatex":
        logger.info("Using %s (detected from magic comment)", engine)
    latex_cmd = [
        engine, "-interaction=nonstopmode",
        "main.tex",
    ]
    pdflatex_log = log_dir / "pdflatex.log" if log_dir else None
    pdf_path = latex_dir / "main.pdf"

    # Remove stale .bbl if .bib is newer, so pdflatex doesn't choke on it
    bbl = latex_dir / "main.bbl"
    bib_files = list(latex_dir.glob("*.bib"))
    if bbl.exists() and bib_files:
        bbl_mtime = bbl.stat().st_mtime
        if any(b.stat().st_mtime > bbl_mtime for b in bib_files):
            bbl.unlink()
            logger.info("Removed stale main.bbl (newer .bib found)")

    _normalize_bbl(latex_dir)

    if not _run(latex_cmd, latex_dir, pdflatex_log):
        if not pdf_path.exists():
            return False
        logger.warning("pdflatex exited with errors but produced a PDF — continuing")

    aux_path = latex_dir / "main.aux"
    aux_has_citations = aux_path.exists() and "\\citation{" in aux_path.read_text()

    if (latex_dir / "main.bcf").exists():
        logger.info("Detected biblatex/biber (.bcf present)")
        bib_log = log_dir / "biber.log" if log_dir else None
        bib_ok = _run(["biber", "main"], latex_dir, bib_log)
    elif aux_has_citations:
        logger.info("Using bibtex")
        bib_log = log_dir / "bibtex.log" if log_dir else None
        bib_ok = _run(["bibtex", "main"], latex_dir, bib_log)
    else:
        logger.info("No bibliography commands found in .aux — skipping bibtex")
        bib_ok = True

    if not bib_ok:
        return False

    _normalize_bbl(latex_dir)

    if not _run(latex_cmd, latex_dir, pdflatex_log):
        if not pdf_path.exists():
            return False
        logger.warning("pdflatex exited with errors but produced a PDF — continuing")
    if not _run(latex_cmd, latex_dir, pdflatex_log):
        if not pdf_path.exists():
            return False
        logger.warning("pdflatex exited with errors but produced a PDF — continuing")

    # Copy TeX's own detailed log files into log_dir
    if log_dir:
        for src, dst in [
            (latex_dir / "main.log",  log_dir / "latex.log"),
            (latex_dir / "main.blg",  log_dir / "bib.log"),
        ]:
            if src.exists():
                shutil.copy2(src, dst)

    return True


def prepare(source: Path, fix_problems: bool = False, force: bool = False,
            log_dir: Path | None = None, workspace_dir: Path | None = None) -> bool:
    """Validate and compile a LaTeX source directory.

    If workspace_dir is provided, the workspace is assumed to already exist
    (created by prepare_workspace). Otherwise a temporary workspace is created
    for backward compatibility with the CLI.

    Returns True if the source is ready for JATS conversion (main.bbl exists),
    False if a fatal error was encountered.
    """
    try:
        main_tex = _find_main_tex(source)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return False

    latex_dir = main_tex.parent
    logger.info("Source directory: %s", latex_dir)

    # Structural validation
    for warning in validate_structure(latex_dir):
        logger.warning("%s", warning)

    if "main.tex not found" in validate_structure(latex_dir):
        return False

    if not force and not _needs_compilation(latex_dir):
        logger.info("main.pdf and main.bbl are up to date; skipping compilation "
                    "(use --force to recompile)")
        return True

    # Use provided workspace or create a temporary one (CLI path)
    if workspace_dir is not None:
        ws = workspace_dir
    else:
        import tempfile
        _tmpdir = tempfile.mkdtemp()
        ws = Path(_tmpdir) / "src"
        prepare_workspace(latex_dir, ws, fix_problems=fix_problems)

    try:
        logger.info("Compiling LaTeX...")
        ok = compile_latex(ws, log_dir=log_dir)
        if ok:
            logger.info("Compilation succeeded.")
            for name in ("main.pdf", "main.bbl", "main.aux"):
                src = ws / name
                if src.exists():
                    shutil.copy2(src, latex_dir / name)
        else:
            logger.error("Compilation failed — check the LaTeX log in %s",
                         log_dir if log_dir else latex_dir)
        return ok
    finally:
        if workspace_dir is None:
            shutil.rmtree(Path(_tmpdir), ignore_errors=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Validate and compile a LaTeX source directory for JATS conversion."
    )
    parser.add_argument("source", help="Source directory or main.tex file")
    parser.add_argument(
        "--fix-simple-problems", action="store_true",
        help="Apply fix-input source fixes in-place before compiling",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompile even if main.pdf and main.bbl are already up to date",
    )
    parser.add_argument(
        "--log-dir", metavar="DIR",
        help="Directory to write compilation logs (pdflatex.log, biber.log, latex.log, bib.log)",
    )
    args = parser.parse_args()

    log_dir = Path(args.log_dir) if args.log_dir else None
    ok = prepare(Path(args.source), fix_problems=args.fix_simple_problems,
                 force=args.force, log_dir=log_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
