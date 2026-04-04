"""Run the prepare → compile → convert → validate pipeline for example articles.

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

from latex_jats.convert import convert, get_doi_suffix, preprocess_for_latexml, validate_jats
from latex_jats.prepare_source import compile_latex, prepare_workspace

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


def needs_compile(example_dir: Path, output_dir: Path) -> bool:
    """Check if the compile step needs to run."""
    compile_dir = output_dir / "compile"
    status_file = compile_dir / "status.json"
    if not status_file.exists():
        return True
    try:
        status = json.loads(status_file.read_text())
        if not status.get("success"):
            return True
    except (json.JSONDecodeError, KeyError):
        return True
    # Check that PDF exists in the output tree
    if not list(compile_dir.glob("*.pdf")):
        return True
    # Check if any .tex file is newer than the PDF
    pdf_mtime = max(f.stat().st_mtime for f in compile_dir.glob("*.pdf"))
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


def _compile_in_workspace(workspace_dir: Path, source_dir: Path,
                          log_dir: Path) -> bool:
    """Compile LaTeX in the workspace and copy outputs back to source."""
    logger.info("Compiling LaTeX...")
    ok = compile_latex(workspace_dir, log_dir=log_dir)
    if ok:
        logger.info("Compilation succeeded.")
        for name in ("main.pdf", "main.bbl", "main.aux"):
            src = workspace_dir / name
            if src.exists():
                shutil.copy2(src, source_dir / name)
    else:
        logger.error("Compilation failed — check the LaTeX log in %s", log_dir)
    return ok


def run_compile(example_dir: Path, output_dir: Path, workspace_dir: Path) -> StepResult:
    """Run the compile step in the workspace and copy PDF to output tree."""
    compile_dir = output_dir / "compile"

    result = _capture_step(
        "compile",
        output_dir,
        _compile_in_workspace,
        workspace_dir,
        example_dir,
        compile_dir,
    )

    # Copy PDF from source dir to output as <article-id>.pdf
    if result.success:
        pdf_src = example_dir / "main.pdf"
        if pdf_src.exists():
            article_id = example_dir.name
            shutil.copy2(pdf_src, compile_dir / f"{article_id}.pdf")
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


def _preprocess_and_convert(workspace_tex: Path, output_xml: Path, **kwargs):
    """Apply LaTeXML preprocessing to the workspace, then convert."""
    n_blocks = preprocess_for_latexml(workspace_tex.parent)
    if n_blocks:
        logger.info(
            "Preprocessed %d #ignoreforxml/#onlyforxml block(s) before LaTeXML conversion",
            n_blocks,
        )
    convert(workspace_tex, output_xml, **kwargs)


def run_convert(example_dir: Path, output_dir: Path, workspace_dir: Path) -> StepResult:
    """Run the JATS conversion step using the workspace."""
    workspace_tex = workspace_dir / "main.tex"
    doi_suffix = get_doi_suffix(workspace_tex)
    convert_dir = output_dir / "convert"
    output_xml = convert_dir / f"{doi_suffix}.xml"

    # Derive lastpage from the PDF produced in the compile step
    lastpage = None
    pdf_files = list((output_dir / "compile").glob("*.pdf"))
    if pdf_files:
        lastpage = _pdf_page_count(pdf_files[0])

    result = _capture_step(
        "convert",
        output_dir,
        _preprocess_and_convert,
        workspace_tex,
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
    """Run prepare → compile → convert → validate for one article."""
    article_id = example_dir.name
    output_dir = OUTPUT_DIR / article_id
    results = []

    do_compile = force or needs_compile(example_dir, output_dir)
    do_convert = force or force_convert or needs_convert(example_dir, output_dir)

    # Step 1: prepare workspace (shared by compile and convert)
    workspace_dir = output_dir / "workspace"
    if do_compile:
        # Source changed — recreate workspace from scratch
        logger.info("--- %s: prepare ---", article_id)
        result = _capture_step(
            "prepare", output_dir,
            prepare_workspace, example_dir, workspace_dir, fix_problems=fix,
        )
        results.append(result)
        if not result.success:
            logger.error("FAILED (prepare): %s", article_id)
            _write_article_status(output_dir, results)
            return results
        logger.info("OK (prepare): %s (%.1fs)", article_id, result.duration_s)
    elif do_convert and not workspace_dir.exists():
        # Convert needed but no workspace yet (e.g. first run with --force-convert)
        logger.info("--- %s: prepare ---", article_id)
        result = _capture_step(
            "prepare", output_dir,
            prepare_workspace, example_dir, workspace_dir, fix_problems=fix,
        )
        results.append(result)
        if not result.success:
            logger.error("FAILED (prepare): %s", article_id)
            _write_article_status(output_dir, results)
            return results
        logger.info("OK (prepare): %s (%.1fs)", article_id, result.duration_s)

    # Step 2: compile
    if do_compile:
        logger.info("--- %s: compile ---", article_id)
        result = run_compile(example_dir, output_dir, workspace_dir)
        results.append(result)
        if not result.success:
            logger.error("FAILED (compile): %s", article_id)
            _write_article_status(output_dir, results)
            return results
        logger.info("OK (compile): %s (%.1fs)", article_id, result.duration_s)
    else:
        logger.info("--- %s: compile (up to date, skipping) ---", article_id)

    # Step 2: convert
    if do_convert:
        logger.info("--- %s: convert ---", article_id)
        result = run_convert(example_dir, output_dir, workspace_dir)
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
        "body { font-family: sans-serif; max-width: 1100px; margin: 2em auto; }",
        ".ok { color: green; } .note { color: green; } .warn { color: #b8860b; } .errors { color: #d94000; } .fail { color: red; } .skip { color: gray; }",
        "table { border-collapse: collapse; width: 100%; }",
        "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; white-space: nowrap; }",
        "button.status-btn { background: none; border: none; cursor: pointer; font: inherit;"
        " border-bottom: 1px dotted currentColor; padding: 0; }",
        # Modal styles
        ".modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100;"
        " justify-content: center; align-items: center; }",
        ".modal-overlay.open { display: flex; }",
        ".modal { background: #1a1a2e; color: #e0e0e0; border-radius: 6px; width: 90vw; max-width: 900px;"
        " max-height: 80vh; display: flex; flex-direction: column; box-shadow: 0 4px 24px rgba(0,0,0,.5); }",
        ".modal-header { display: flex; justify-content: space-between; align-items: center;"
        " padding: 10px 16px; border-bottom: 1px solid #444; }",
        ".modal-header h3 { margin: 0; font-size: 14px; }",
        ".modal-close { background: none; border: none; color: #e0e0e0; font-size: 20px; cursor: pointer; padding: 0 4px; }",
        ".modal-tabs { display: flex; gap: 0; border-bottom: 1px solid #444; padding: 0 16px; }",
        ".modal-tabs button { background: none; border: none; color: #999; padding: 8px 14px; cursor: pointer;"
        " font: 12px/1.4 monospace; border-bottom: 2px solid transparent; margin-bottom: -1px; }",
        ".modal-tabs button.active { color: #e0e0e0; border-bottom-color: #7c8aff; }",
        ".modal-body { overflow: auto; flex: 1; }",
        ".modal-body pre { margin: 0; padding: 12px 16px; white-space: pre-wrap; word-break: break-all;"
        " font: 12px/1.4 monospace; }",
        ".tab-panel { display: none; } .tab-panel.active { display: block; }",
        "</style>",
        "</head><body>",
        "<h1>CCR Article Previews</h1>",
        "<table><tr><th>Article</th><th>HTML</th><th>XML</th><th>PDF</th><th>Prepare</th><th>Compile</th><th>Convert</th><th>Validate</th></tr>",
    ]

    for article_dir in articles:
        article = article_dir.name
        prepare_dir = article_dir / "prepare"
        compile_dir = article_dir / "compile"
        convert_dir = article_dir / "convert"
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
        if compile_dir.exists():
            for f in compile_dir.glob("*.pdf"):
                pdf_link = f'<a href="{article}/compile/{f.name}">PDF</a>'
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
            n_errors = n_warnings = n_fixes = 0
            runner_text = ""
            if runner_log.exists():
                runner_text = runner_log.read_text(errors="replace")
                if success:
                    for line in runner_text.splitlines():
                        if line.startswith("INFO: FIXED"):
                            n_fixes += 1
                        elif line.startswith("WARNING:"):
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
                if n_fixes:
                    parts.append(f"{n_fixes} fix{'es' if n_fixes != 1 else ''}")
                css, label = "errors", ", ".join(parts)
            elif n_warnings or n_fixes:
                parts = []
                if n_warnings:
                    parts.append(f"{n_warnings} warning{'s' if n_warnings != 1 else ''}")
                if n_fixes:
                    parts.append(f"{n_fixes} fix{'es' if n_fixes != 1 else ''}")
                css, label = ("warn" if n_warnings else "note"), ", ".join(parts)
            else:
                css, label = "ok", "ok"
            import html as html_mod
            # Collect all log tabs: runner first, then others
            tabs: list[tuple[str, str]] = []  # (tab_label, content)
            if runner_text.strip():
                tabs.append(("runner", html_mod.escape(runner_text.strip())))
            for log_file in sorted(step_dir.rglob("*.log")):
                if log_file.name == "runner.log":
                    continue
                stem = log_file.stem
                for known in ("latexml", "latexmlpost"):
                    if known in stem:
                        stem = stem[stem.index(known):]
                        break
                content = log_file.read_text(errors="replace").strip()
                if content:
                    tabs.append((stem, html_mod.escape(content)))
            if not tabs:
                return f'<span class="{css}">{label}</span>'
            modal_id = f"modal-{article}-{step_dir.name}"
            # Build modal HTML
            tab_buttons = "".join(
                f'<button class="{"active" if i == 0 else ""}" data-tab="{modal_id}-{i}">{t[0]}</button>'
                for i, t in enumerate(tabs)
            )
            tab_panels = "".join(
                f'<div id="{modal_id}-{i}" class="tab-panel {"active" if i == 0 else ""}"><pre>{t[1]}</pre></div>'
                for i, t in enumerate(tabs)
            )
            modal = (
                f'<div id="{modal_id}" class="modal-overlay" onclick="if(event.target===this)this.classList.remove(\'open\')">'
                f'<div class="modal"><div class="modal-header">'
                f"<h3>{article} / {step_dir.name}</h3>"
                f'<button class="modal-close" onclick="this.closest(\'.modal-overlay\').classList.remove(\'open\')">&times;</button>'
                f'</div><div class="modal-tabs">{tab_buttons}</div>'
                f'<div class="modal-body">{tab_panels}</div></div></div>'
            )
            btn = f'<button class="status-btn {css}" onclick="document.getElementById(\'{modal_id}\').classList.add(\'open\')">{label}</button>'
            return btn + modal

        lines.append(
            f"<tr><td><strong>{article}</strong></td>"
            f"<td>{html_link}</td><td>{xml_link}</td><td>{pdf_link}</td>"
            f"<td>{_step_cell(prepare_dir)}</td>"
            f"<td>{_step_cell(compile_dir)}</td>"
            f"<td>{_step_cell(convert_dir)}</td>"
            f"<td>{_step_cell(validate_dir)}</td></tr>"
        )

    lines.append("</table>")
    lines.append(
        "<script>"
        "document.addEventListener('click',function(e){"
        "if(!e.target.matches('.modal-tabs button'))return;"
        "var tabs=e.target.parentElement,body=tabs.nextElementSibling;"
        "tabs.querySelectorAll('button').forEach(function(b){b.classList.remove('active')});"
        "body.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active')});"
        "e.target.classList.add('active');"
        "document.getElementById(e.target.dataset.tab).classList.add('active');"
        "});"
        "document.addEventListener('keydown',function(e){"
        "if(e.key==='Escape'){var m=document.querySelector('.modal-overlay.open');if(m)m.classList.remove('open');}"
        "});"
        "</script>"
    )
    lines.append("</body></html>")
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
