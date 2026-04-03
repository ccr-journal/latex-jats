"""Run the prepare-source and convert steps for example articles.

Provides incremental builds: each step is skipped if its output is already
up-to-date. Results and logs are written to a centralized output/ tree at the
project root.

Usage:
    uv run run-examples                       # run all examples
    uv run run-examples CCR2023.1.004.KATH    # run one example
    uv run run-examples --force               # rerun everything
    uv run run-examples --force-convert       # only force the convert step
"""

import argparse
import io
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from latex_jats.convert import convert, get_doi_suffix, validate_jats
from latex_jats.prepare_source import _needs_compilation, prepare

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "examples"
OUTPUT_DIR = PROJECT_ROOT / "output"


@dataclass
class StepResult:
    step: str
    success: bool
    duration_s: float
    timestamp: str
    log_file: str | None = None


def find_examples(specific: str | None = None) -> list[Path]:
    """Return example directories (all CCR* or a single one).

    Accepts a bare folder name (e.g. CCR2025.1.2.YAO) or a path
    (e.g. examples/CCR2025.1.2.YAO/ or an absolute path).
    """
    if specific:
        # Strip trailing slash and try as a direct path first
        as_path = Path(specific.rstrip("/"))
        if as_path.is_dir():
            return [as_path.resolve()]
        # Fall back to treating it as a folder name under EXAMPLES_DIR
        candidate = EXAMPLES_DIR / as_path.name
        if not candidate.is_dir():
            # Try suffix match (e.g. "WEDE" matches "CCR2026.1.3.WEDE")
            suffix = as_path.name.upper()
            matches = [d for d in EXAMPLES_DIR.iterdir()
                       if d.is_dir() and d.name.upper().endswith(suffix)]
            if len(matches) == 1:
                return [matches[0]]
            if len(matches) > 1:
                names = ', '.join(d.name for d in sorted(matches))
                raise FileNotFoundError(f"Ambiguous example suffix {specific!r}: {names}")
            raise FileNotFoundError(f"Example not found: {candidate}")
        return [candidate]
    return sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir() and p.name.startswith("CCR") and (p / "main.tex").exists())


def _newest_tex_mtime(example_dir: Path) -> float:
    """Return the newest mtime of any .tex file in the example directory."""
    tex_files = list(example_dir.glob("*.tex")) + list(example_dir.glob("**/*.tex"))
    return max((f.stat().st_mtime for f in tex_files), default=0)


def needs_prepare(example_dir: Path, output_dir: Path) -> bool:
    """Check if the prepare step needs to run."""
    prepare_dir = output_dir / "prepare"
    status_file = prepare_dir / "status.json"
    if not status_file.exists():
        return True
    try:
        status = json.loads(status_file.read_text())
        if not status.get("success"):
            return True
    except (json.JSONDecodeError, KeyError):
        return True
    # Check that PDF exists in the output tree
    if not list(prepare_dir.glob("*.pdf")):
        return True
    # Check if any .tex file is newer than the PDF
    pdf_mtime = max(f.stat().st_mtime for f in prepare_dir.glob("*.pdf"))
    if _newest_tex_mtime(example_dir) > pdf_mtime:
        return True
    return False


def needs_convert(example_dir: Path, output_dir: Path) -> bool:
    """Check if the convert step needs to run."""
    convert_dir = output_dir / "convert"
    status_file = convert_dir / "status.json"
    if not status_file.exists():
        return True
    try:
        status = json.loads(status_file.read_text())
        if not status.get("success"):
            return True
    except (json.JSONDecodeError, KeyError):
        return True
    # Check if any XML exists
    xml_files = list(convert_dir.glob("*.xml"))
    if not xml_files:
        return True
    xml_mtime = min(f.stat().st_mtime for f in xml_files)
    # Stale if .tex or .bbl is newer than the XML
    if _newest_tex_mtime(example_dir) > xml_mtime:
        return True
    bbl = example_dir / "main.bbl"
    if bbl.exists() and bbl.stat().st_mtime > xml_mtime:
        return True
    return False


def _capture_step(step_name: str, output_dir: Path, func, *args, **kwargs) -> StepResult:
    """Run func with captured logging output, write status.json and log file."""
    step_dir = output_dir / step_name
    step_dir.mkdir(parents=True, exist_ok=True)
    log_path = step_dir / "runner.log"

    # Set up log capture for this step
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    handler.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    start = time.monotonic()
    success = False
    try:
        result = func(*args, **kwargs)
        # prepare() returns bool; convert()/validate_jats() return other types
        success = result if isinstance(result, bool) else True
    except Exception:
        logger.exception("Step '%s' raised an exception", step_name)
        success = False
    finally:
        duration = time.monotonic() - start
        root_logger.removeHandler(handler)

    # Write captured log
    log_path.write_text(log_stream.getvalue(), encoding="utf-8")

    # Write status
    step_result = StepResult(
        step=step_name,
        success=success,
        duration_s=round(duration, 1),
        timestamp=datetime.now(timezone.utc).isoformat(),
        log_file=str(log_path.relative_to(output_dir)),
    )
    (step_dir / "status.json").write_text(json.dumps(asdict(step_result), indent=2), encoding="utf-8")
    return step_result


def run_prepare(example_dir: Path, output_dir: Path, force: bool = False,
                fix: bool = False) -> StepResult:
    """Run the prepare-source step and copy PDF to output tree."""
    prepare_dir = output_dir / "prepare"
    runner_log = prepare_dir / "runner.log"
    old_log = runner_log.read_text(encoding="utf-8") if runner_log.exists() else None

    result = _capture_step(
        "prepare",
        output_dir,
        prepare,
        example_dir,
        fix_problems=fix,
        force=force,
        log_dir=prepare_dir,
    )

    # If prepare() skipped compilation (files up to date), restore the old
    # runner.log so the detailed output from the actual compile run is preserved.
    if old_log and result.success and "skipping compilation" in runner_log.read_text(encoding="utf-8", errors="replace"):
        runner_log.write_text(old_log, encoding="utf-8")
    # Copy PDF from source dir to output as <article-id>.pdf
    if result.success:
        pdf_src = example_dir / "main.pdf"
        if pdf_src.exists():
            article_id = example_dir.name
            shutil.copy2(pdf_src, prepare_dir / f"{article_id}.pdf")
    return result


def _pdf_page_count(pdf_path: Path) -> int | None:
    """Return the number of pages in a PDF using pdfinfo, or None on failure."""
    import shutil
    import subprocess
    if not shutil.which("pdfinfo"):
        return None
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return None


def run_convert(example_dir: Path, output_dir: Path, force: bool = False) -> StepResult:
    """Run the JATS conversion step."""
    main_tex = example_dir / "main.tex"
    doi_suffix = get_doi_suffix(main_tex)
    convert_dir = output_dir / "convert"
    output_xml = convert_dir / f"{doi_suffix}.xml"

    # Derive lastpage from the PDF produced in the prepare step
    lastpage = None
    pdf_files = list((output_dir / "prepare").glob("*.pdf"))
    if pdf_files:
        lastpage = _pdf_page_count(pdf_files[0])

    result = _capture_step(
        "convert",
        output_dir,
        convert,
        main_tex,
        output_xml,
        html=True,
        lastpage=lastpage,
    )

    return result


def _validate_wrapper(xml_file: str) -> bool:
    """Wrapper around validate_jats that returns bool for _capture_step."""
    errors = validate_jats(xml_file)
    if errors:
        logger.warning("%d JATS validation error(s)", len(errors))
        return False
    return True


def run_validate(example_dir: Path, output_dir: Path) -> StepResult:
    """Run JATS validation as a separate step."""
    main_tex = example_dir / "main.tex"
    doi_suffix = get_doi_suffix(main_tex)
    convert_dir = output_dir / "convert"
    xml_file = convert_dir / f"{doi_suffix}.xml"
    return _capture_step("validate", output_dir, _validate_wrapper, str(xml_file))


def run_article(example_dir: Path, force: bool = False, force_convert: bool = False,
                fix: bool = False) -> list[StepResult]:
    """Run prepare then convert for one article. Stop on first failure."""
    article_id = example_dir.name
    output_dir = OUTPUT_DIR / article_id
    results = []

    # Step 1: prepare
    if force or needs_prepare(example_dir, output_dir):
        logger.info("--- %s: prepare ---", article_id)
        result = run_prepare(example_dir, output_dir, force=force, fix=fix)
        results.append(result)
        if not result.success:
            logger.error("FAILED (prepare): %s", article_id)
            _write_article_status(output_dir, results)
            return results
        logger.info("OK (prepare): %s (%.1fs)", article_id, result.duration_s)
    else:
        logger.info("--- %s: prepare (up to date, skipping) ---", article_id)

    # Step 2: convert
    if force or force_convert or needs_convert(example_dir, output_dir):
        logger.info("--- %s: convert ---", article_id)
        result = run_convert(example_dir, output_dir, force=force or force_convert)
        results.append(result)
        if not result.success:
            logger.error("FAILED (convert): %s", article_id)
            _write_article_status(output_dir, results)
            return results
        logger.info("OK (convert): %s (%.1fs)", article_id, result.duration_s)
        ran_convert = True
    else:
        logger.info("--- %s: convert (up to date, skipping) ---", article_id)
        ran_convert = False

    # Step 3: validate (re-run if convert ran, or if validate hasn't run yet)
    validate_status = output_dir / "validate" / "status.json"
    if ran_convert or not validate_status.exists():
        logger.info("--- %s: validate ---", article_id)
        result = run_validate(example_dir, output_dir)
        results.append(result)
        if result.success:
            logger.info("OK (validate): %s", article_id)
        else:
            logger.warning("WARN (validate): %s has validation errors", article_id)
    else:
        logger.info("--- %s: validate (up to date, skipping) ---", article_id)

    if results:
        _write_article_status(output_dir, results)
    return results


def _write_article_status(output_dir: Path, results: list[StepResult]):
    """Write article-level status.json, merging with existing status for skipped steps."""
    output_dir.mkdir(parents=True, exist_ok=True)
    status_file = output_dir / "status.json"
    # Load existing status so skipped steps are preserved
    existing = {}
    if status_file.exists():
        try:
            existing = json.loads(status_file.read_text()).get("steps", {})
        except (json.JSONDecodeError, KeyError):
            pass
    # Merge new results
    for r in results:
        existing[r.step] = "success" if r.success else "failed"
    status_file.write_text(json.dumps({"steps": existing}, indent=2), encoding="utf-8")


def generate_index(output_root: Path):
    """Generate index.html from status.json files with links to outputs."""
    articles = sorted(p for p in output_root.iterdir() if p.is_dir() and p.name.startswith("CCR"))

    lines = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        "<title>CCR Preview</title>",
        "<style>",
        "body { font-family: sans-serif; max-width: 900px; margin: 2em auto; }",
        ".ok { color: green; } .note { color: #b8860b; } .warn { color: orange; } .fail { color: red; } .skip { color: gray; }",
        "table { border-collapse: collapse; width: 100%; }",
        "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; white-space: nowrap; }",
        "</style>",
        "</head><body>",
        "<h1>CCR Article Previews</h1>",
        "<table><tr><th>Article</th><th>HTML</th><th>XML</th><th>PDF</th><th>Prepare</th><th>Convert</th><th>Validate</th></tr>",
    ]

    for article_dir in articles:
        article = article_dir.name
        convert_dir = article_dir / "convert"
        prepare_dir = article_dir / "prepare"
        validate_dir = article_dir / "validate"

        # Output links (HTML, XML, PDF) as separate cells
        html_link = "-"
        xml_link = "-"
        pdf_link = "-"
        if convert_dir.exists():
            for f in convert_dir.glob("*.html"):
                html_link = f'<a href="{article}/convert/{f.name}">HTML</a>'
                break
            for f in convert_dir.glob("*.xml"):
                xml_link = f'<a href="{article}/convert/{f.name}">XML</a>'
                break
        if prepare_dir.exists():
            for f in prepare_dir.glob("*.pdf"):
                pdf_link = f'<a href="{article}/prepare/{f.name}">PDF</a>'
                break

        # Per-step log links + status
        def _step_cell(step_dir: Path) -> str:
            status_file = step_dir / "status.json"
            if not status_file.exists():
                return '<span class="skip">-</span>'
            try:
                data = json.loads(status_file.read_text())
                success = data.get("success")
            except (json.JSONDecodeError, KeyError):
                success = None
            runner_log = step_dir / "runner.log"
            n_errors = n_warnings = 0
            if success and runner_log.exists():
                for line in runner_log.read_text(errors="replace").splitlines():
                    if not line.startswith("WARNING:"):
                        continue
                    if "WARNING: LaTeXML: Error:" in line:
                        n_errors += 1
                    else:
                        n_warnings += 1
            if not success:
                css, label = ("fail" if success is False else "skip"), ("failed" if success is False else "?")
            elif n_errors:
                parts = [f"{n_errors} error{'s' if n_errors != 1 else ''}"]
                if n_warnings:
                    parts.append(f"{n_warnings} warning{'s' if n_warnings != 1 else ''}")
                css, label = "warn", ", ".join(parts)
            elif n_warnings:
                css, label = "note", f"{n_warnings} warning{'s' if n_warnings != 1 else ''}"
            else:
                css, label = "ok", "ok"
            result = f'<span class="{css}">{label}</span>'
            log_links = []
            for log_file in sorted(step_dir.rglob("*.log")):
                rel = log_file.relative_to(article_dir)
                # Strip everything before known log names (e.g. CCR2025.1.12.CROS.latexml -> latexml)
                stem = log_file.stem
                for known in ("latexml", "latexmlpost"):
                    if known in stem:
                        stem = stem[stem.index(known):]
                        break
                log_links.append(f'<a href="{article}/{rel}">{stem}</a>')
            log_html = " ".join(log_links)
            return f"{result} [logs: {log_html}]"

        lines.append(
            f"<tr><td><strong>{article}</strong></td>"
            f"<td>{html_link}</td><td>{xml_link}</td><td>{pdf_link}</td>"
            f"<td>{_step_cell(prepare_dir)}</td>"
            f"<td>{_step_cell(convert_dir)}</td>"
            f"<td>{_step_cell(validate_dir)}</td></tr>"
        )

    lines.append("</table></body></html>")
    (output_root / "index.html").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Generated %s", output_root / "index.html")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Run prepare and convert steps for example articles.")
    parser.add_argument(
        "example",
        nargs="?",
        help="Run a single example (folder name under examples/). Omit to run all.",
    )
    parser.add_argument("--force", action="store_true", help="Rerun all steps")
    parser.add_argument("--force-convert", action="store_true", help="Force only the convert step")
    parser.add_argument("--fix", action="store_true",
                        help="Apply simple source fixes (unescaped &, bare <>, etc.) before compiling")
    args = parser.parse_args()

    examples = find_examples(args.example)
    logger.info("Found %d example(s) to process", len(examples))

    all_results = {}
    for example_dir in examples:
        results = run_article(
            example_dir,
            force=args.force,
            force_convert=args.force_convert,
            fix=args.fix,
        )
        all_results[example_dir.name] = results

    # Generate index.html
    generate_index(OUTPUT_DIR)

    # Summary
    failed = [name for name, results in all_results.items() if any(not r.success for r in results)]
    if failed:
        logger.warning("Failed articles: %s", ", ".join(failed))
    else:
        logger.info("All articles processed successfully.")


if __name__ == "__main__":
    main()
