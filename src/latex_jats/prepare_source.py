"""Validate and prepare a LaTeX source directory for JATS conversion.

Checks that the source folder is well-formed, optionally applies source fixes,
and compiles the LaTeX document (pdflatex + biber/bibtex) to produce:
  - main.pdf  — for the web preview
  - main.bbl  — required by the JATS converter

Compilation is skipped when both main.pdf and main.bbl are already present and
newer than all .tex files in the directory, unless --force is given.

Usage:
    uv run prepare-source path/to/latex/          # validate + compile if needed
    uv run prepare-source path/to/main.tex        # same, accepts file too
    uv run prepare-source path/to/latex/ --fix-simple-problems
    uv run prepare-source path/to/latex/ --force
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

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


def compile_latex(latex_dir: Path, log_dir: Path | None = None) -> bool:
    """Run pdflatex → biber/bibtex → pdflatex → pdflatex.

    Detects biber vs bibtex by checking for main.bcf after the first pdflatex
    run (biblatex writes a .bcf control file; plain bibtex does not).

    If log_dir is given, stdout/stderr of each step is captured there and
    pdflatex's main.log / biber's main.blg are also copied in.

    Returns True if compilation succeeded.
    """
    import shutil

    pdflatex = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    pdflatex_log = log_dir / "pdflatex.log" if log_dir else None

    # Remove stale .bbl if .bib is newer, so pdflatex doesn't choke on it
    bbl = latex_dir / "main.bbl"
    bib_files = list(latex_dir.glob("*.bib"))
    if bbl.exists() and bib_files:
        bbl_mtime = bbl.stat().st_mtime
        if any(b.stat().st_mtime > bbl_mtime for b in bib_files):
            bbl.unlink()
            logger.info("Removed stale main.bbl (newer .bib found)")

    if not _run(pdflatex, latex_dir, pdflatex_log):
        return False

    if (latex_dir / "main.bcf").exists():
        logger.info("Detected biblatex/biber (.bcf present)")
        bib_log = log_dir / "biber.log" if log_dir else None
        bib_ok = _run(["biber", "main"], latex_dir, bib_log)
    else:
        logger.info("Using bibtex")
        bib_log = log_dir / "bibtex.log" if log_dir else None
        bib_ok = _run(["bibtex", "main"], latex_dir, bib_log)

    if not bib_ok:
        return False

    if not _run(pdflatex, latex_dir, pdflatex_log):
        return False
    if not _run(pdflatex, latex_dir, pdflatex_log):
        return False

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
            log_dir: Path | None = None) -> bool:
    """Validate and compile a LaTeX source directory.

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

    # Optional source fixes
    fixed = 0
    if fix_problems:
        logger.info("Applying source fixes (--fix-simple-problems)...")
        for tex_file in _collect_tex_files(main_tex):
            fixed += fix_file(tex_file, apply=True)
        if fixed:
            logger.info("Fixed %d line(s); will recompile.", fixed)
        else:
            logger.info("No source fixes needed.")

    # Compilation
    if not force and not fixed and not _needs_compilation(latex_dir):
        logger.info("main.pdf and main.bbl are up to date; skipping compilation "
                    "(use --force to recompile)")
        return True

    logger.info("Compiling LaTeX...")
    ok = compile_latex(latex_dir, log_dir=log_dir)
    if ok:
        logger.info("Compilation succeeded.")
    else:
        logger.error("Compilation failed — check the LaTeX log in %s",
                     log_dir if log_dir else latex_dir)
    return ok


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
