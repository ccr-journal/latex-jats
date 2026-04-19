"""Background pipeline runner.

Called from the upload route via FastAPI BackgroundTasks.  Runs the full
prepare → compile → convert → validate pipeline and updates the Manuscript row
with status transitions and captured log output.
"""

import logging
import shutil
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

import re

from sqlmodel import select

from latex_jats.convert import (
    compare_metadata,
    convert,
    create_publisher_zip,
    get_doi_suffix,
    preprocess_for_latexml,
    validate_jats,
)
from latex_jats.prepare_source import compile_latex, prepare_workspace
from latex_jats.quarto import (
    convert_quarto,
    find_qmd,
    get_doi_suffix_from_qmd,
    prepare_quarto_workspace,
    render_quarto_pdf,
)

from .models import (
    Manuscript, ManuscriptAuthor, ManuscriptStatus, PIPELINE_STEPS, StepStatus,
)
from .storage import Storage

logger = logging.getLogger(__name__)

# LaTeX macro name → Manuscript field name
_OJS_MACRO_MAP = {
    "doi": "doi",
    "volume": "volume",
    "pubnumber": "issue_number",
    "pubyear": "year",
    "firstpage": None,  # default to "1" if missing
}


def inject_ojs_metadata(tex_file: Path, manuscript) -> None:
    """Inject missing journal metadata macros into the LaTeX preamble.

    For each macro in _OJS_MACRO_MAP, if it is absent from the preamble and
    the manuscript has a value for it, the macro is inserted before
    ``\\begin{document}``.  Existing macros are never overwritten — mismatches
    are caught later by compare_metadata.
    """
    text = tex_file.read_text(encoding="utf-8")
    parts = text.split(r"\begin{document}", 1)
    if len(parts) != 2:
        return  # no \begin{document} found

    preamble, rest = parts
    injected: list[str] = []

    for macro, field in _OJS_MACRO_MAP.items():
        # Check if macro already present in preamble
        if re.search(r'\\' + macro + r'\s*\{', preamble):
            continue
        if field is not None:
            value = getattr(manuscript, field, None)
            if value is None:
                continue
            value = str(value)
        else:
            # firstpage: inject default "1" if missing
            value = "1"
        injected.append(rf"\{macro}{{{value}}}")

    if injected:
        insert_block = "\n% Injected from OJS metadata\n" + "\n".join(injected) + "\n"
        text = preamble + insert_block + r"\begin{document}" + rest
        tex_file.write_text(text, encoding="utf-8")
        pipeline_logger = logging.getLogger("latex_jats")
        pipeline_logger.info("Injected missing metadata from OJS: %s",
                             ", ".join(injected))


class _LogCollector(logging.Handler):
    """Collects log records from the ``latex_jats`` logger hierarchy.

    When multiple pipelines run concurrently (FastAPI BackgroundTasks run in
    a shared thread pool), every collector is attached to the same
    ``latex_jats`` logger and would otherwise receive every pipeline's
    records.  We capture the thread that created the collector and ignore
    records emitted from other threads — each pipeline's work (including the
    subprocess captures that route back through logging) happens in a single
    thread, so the thread id is a reliable owner marker.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.buffer: list[str] = []
        self._owner_thread = threading.get_ident()

    def emit(self, record: logging.LogRecord) -> None:
        if threading.get_ident() != self._owner_thread:
            return
        self.buffer.append(self.format(record))

    def drain(self) -> str:
        """Return all buffered lines joined by newlines and clear the buffer."""
        text = "\n".join(self.buffer)
        self.buffer.clear()
        return text


def _update_manuscript(engine: Engine, doi_suffix: str, **fields) -> None:
    """Open a short-lived session, update the manuscript, and commit."""
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms is None:
            return
        for key, value in fields.items():
            setattr(ms, key, value)
        ms.updated_at = datetime.utcnow()
        session.add(ms)
        session.commit()


def _append_log(engine: Engine, doi_suffix: str, text: str) -> None:
    """Append text to the manuscript's job_log field."""
    if not text:
        return
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms is None:
            return
        ms.job_log = (ms.job_log + "\n" + text) if ms.job_log else text
        ms.updated_at = datetime.utcnow()
        session.add(ms)
        session.commit()


# ── Step-level progress helpers ──────────────────────────────────────────────


def classify_step_status(log_text: str) -> str:
    """Classify a step's log output into ok/warnings/errors.

    Matches the logic in runner.py ``_step_cell``: counts WARNING and ERROR
    lines, treats ``WARNING: LaTeXML: Error:`` as an error.
    """
    n_errors = n_warnings = 0
    for line in log_text.splitlines():
        if line.startswith("WARNING:"):
            if "LaTeXML: Error:" in line:
                n_errors += 1
            else:
                n_warnings += 1
        elif line.startswith("ERROR:"):
            n_errors += 1
    if n_errors:
        return StepStatus.errors
    if n_warnings:
        return StepStatus.warnings
    return StepStatus.ok


def init_pipeline_steps() -> list[dict]:
    """Return initial pipeline_steps list with all steps pending."""
    return [
        {"name": name, "status": StepStatus.pending, "logs": [],
         "started_at": None, "completed_at": None}
        for name in PIPELINE_STEPS
    ]


def _update_step(engine: Engine, doi_suffix: str, step_name: str, **fields) -> None:
    """Update a single step's fields in the pipeline_steps JSON."""
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms is None or not ms.pipeline_steps:
            return
        # Must create a new list so SQLAlchemy detects the mutation
        steps = [dict(s) for s in ms.pipeline_steps]
        for step in steps:
            if step["name"] == step_name:
                step.update(fields)
                break
        ms.pipeline_steps = steps
        ms.updated_at = datetime.utcnow()
        session.add(ms)
        session.commit()


def _start_step(engine: Engine, doi_suffix: str, step_name: str) -> None:
    """Mark a pipeline step as running."""
    _update_step(engine, doi_suffix, step_name,
                 status=StepStatus.running,
                 started_at=datetime.utcnow().isoformat())


def _collect_log_files(dirs: list[Path]) -> list[dict]:
    """Read .log files from the given directories and return as log entries.

    Matches the runner's tab logic: collects all .log files, uses known
    names (latexml, latexmlpost) when detected in the filename.
    """
    entries = []
    for d in dirs:
        if not d.exists():
            continue
        for log_file in sorted(d.rglob("*.log")):
            content = log_file.read_text(errors="replace").strip()
            if not content:
                continue
            stem = log_file.stem
            for known in ("latexml", "latexmlpost"):
                if known in stem:
                    stem = stem[stem.index(known):]
                    break
            entries.append({"name": stem, "content": content})
    return entries


_PIPELINE_LOG_HEADER = (
    "# This log contains a summary of all warnings and other important "
    "events from this step.\n"
    "# See the other tabs for the raw logs of the individual processes.\n"
)


def _finish_step(engine: Engine, doi_suffix: str, step_name: str,
                 log_text: str, *, failed: bool = False,
                 log_dirs: list[Path] | None = None) -> None:
    """Mark a pipeline step as completed and store its logs."""
    status = StepStatus.failed if failed else classify_step_status(log_text)
    body = log_text.strip() or "(no warnings or errors)"
    logs: list[dict] = [
        {"name": "pipeline", "content": _PIPELINE_LOG_HEADER + "\n" + body}
    ]
    if log_dirs:
        logs.extend(_collect_log_files(log_dirs))
    _update_step(engine, doi_suffix, step_name,
                 status=status,
                 logs=logs,
                 completed_at=datetime.utcnow().isoformat())
    _append_log(engine, doi_suffix, log_text)


def _skip_remaining_steps(engine: Engine, doi_suffix: str, step_names: list[str]) -> None:
    """Mark the listed steps as skipped."""
    for name in step_names:
        _update_step(engine, doi_suffix, name, status=StepStatus.skipped)


def _is_quarto_source(source_dir: Path) -> bool:
    """Return True if the source directory contains .qmd files but no main.tex."""
    return not (source_dir / "main.tex").exists() and bool(list(source_dir.glob("*.qmd")))


def _pdf_page_count(pdf_path) -> int | None:
    """Return the number of pages in a PDF using pdfinfo, or None on failure."""
    if not shutil.which("pdfinfo"):
        return None
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return None


# ── Main pipeline ────────────────────────────────────────────────────────────


def _run_latex_pipeline(
    doi_suffix: str, engine: Engine, storage: Storage, collector: _LogCollector,
    step_tracker: list[str], *, fix: bool = False,
    use_canonical_ccr_cls: bool = False,
) -> None:
    """LaTeX-specific pipeline: prepare → compile → convert → check → validate."""
    source_dir = storage.source_dir(doi_suffix)
    workspace_dir = storage.prepare_output_dir(doi_suffix)
    convert_output = storage.convert_output_dir(doi_suffix)

    # ── Step 1: prepare workspace ────────────────────────────────────
    workspace_tex = prepare_workspace(
        source_dir, workspace_dir,
        fix_problems=fix,
        use_canonical_ccr_cls=use_canonical_ccr_cls,
    )

    # Inject missing journal metadata from OJS before compilation
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms and ms.ojs_submission_id:
            inject_ojs_metadata(workspace_tex, ms)

    _finish_step(engine, doi_suffix, "prepare", collector.drain())

    # ── Step 2: compile LaTeX ────────────────────────────────────────
    step_tracker[0] = "compile"
    _start_step(engine, doi_suffix, "compile")
    log_dir = storage.prepare_output_dir(doi_suffix)
    ok = compile_latex(workspace_dir, log_dir=log_dir)
    _finish_step(engine, doi_suffix, "compile", collector.drain(),
                 failed=not ok, log_dirs=[log_dir])

    if not ok:
        _skip_remaining_steps(engine, doi_suffix, ["convert", "check", "validate"])
        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.failed,
            job_completed_at=datetime.utcnow(),
        )
        return

    # Copy main.pdf back to source_dir for lastpage / future reference
    pdf_src = workspace_dir / "main.pdf"
    if pdf_src.exists():
        shutil.copy2(pdf_src, source_dir / "main.pdf")

    # ── Step 3: convert (preprocess + latexmlc + post-processing + zip)
    step_tracker[0] = "convert"
    _start_step(engine, doi_suffix, "convert")
    preprocess_for_latexml(workspace_dir)

    # Determine article ID from the LaTeX preamble (for validation/logging only)
    try:
        article_id = get_doi_suffix(workspace_tex)
    except Exception:
        article_id = doi_suffix
    if article_id != doi_suffix:
        logger.info(
            "Article ID from LaTeX (%s) differs from manuscript doi_suffix (%s); "
            "output files will be named after doi_suffix",
            article_id, doi_suffix,
        )

    output_xml = convert_output / f"{doi_suffix}.xml"

    lastpage = None
    if pdf_src.exists():
        lastpage = _pdf_page_count(pdf_src)

    convert(workspace_tex, output_xml, html=True, lastpage=lastpage)

    # Copy PDF to convert output for web preview
    pdf_path = source_dir / "main.pdf" if (source_dir / "main.pdf").exists() else None
    if pdf_path:
        shutil.copy2(pdf_path, convert_output / f"{doi_suffix}.pdf")

    # Create publisher zip
    zip_path = convert_output / f"{doi_suffix}.zip"
    create_publisher_zip(output_xml, pdf_path, zip_path)
    convert_log_dir = convert_output / "logs"
    _finish_step(engine, doi_suffix, "convert", collector.drain(),
                 log_dirs=[convert_log_dir])

    # ── Step 4: compare metadata against OJS ────────────────────────
    step_tracker[0] = "check"
    _start_step(engine, doi_suffix, "check")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms and ms.ojs_submission_id:
            ms_authors = session.exec(
                select(ManuscriptAuthor)
                .where(ManuscriptAuthor.manuscript_id == doi_suffix)
                .order_by(ManuscriptAuthor.order)
            ).all()
            compare_metadata(
                output_xml, ms, ms_authors,
                output_json=convert_output / "metadata_comparison.json",
            )
    _finish_step(engine, doi_suffix, "check", collector.drain())

    # ── Step 5: validate JATS XML ────────────────────────────────────
    step_tracker[0] = "validate"
    _start_step(engine, doi_suffix, "validate")
    validate_jats(str(output_xml))
    _finish_step(engine, doi_suffix, "validate", collector.drain())

    # ── Done ─────────────────────────────────────────────────────────
    step_tracker[0] = ""
    _update_manuscript(
        engine,
        doi_suffix,
        status=ManuscriptStatus.ready,
        job_completed_at=datetime.utcnow(),
    )


def _run_quarto_pipeline(
    doi_suffix: str, engine: Engine, storage: Storage, collector: _LogCollector,
    step_tracker: list[str], *, use_canonical_ccr_cls: bool = False,
) -> None:
    """Quarto-specific pipeline: prepare → compile (PDF) → convert → check → validate."""
    source_dir = storage.source_dir(doi_suffix)
    workspace_dir = storage.prepare_output_dir(doi_suffix)
    convert_output = storage.convert_output_dir(doi_suffix)

    # ── Step 1: prepare workspace ────────────────────────────────────
    prepare_quarto_workspace(
        source_dir, workspace_dir,
        use_canonical_ccr_cls=use_canonical_ccr_cls,
    )
    _finish_step(engine, doi_suffix, "prepare", collector.drain())

    workspace_qmd = find_qmd(workspace_dir)
    if workspace_qmd is None:
        raise FileNotFoundError(f"No .qmd file found in {workspace_dir}")

    # ── Step 2: compile PDF (for page count and publisher zip) ───────
    step_tracker[0] = "compile"
    _start_step(engine, doi_suffix, "compile")
    pdf_path = None
    lastpage = None
    try:
        rendered_pdf = render_quarto_pdf(workspace_qmd, log_dir=workspace_dir)
        pdf_path = convert_output / f"{workspace_qmd.stem}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_pdf, pdf_path)
        lastpage = _pdf_page_count(pdf_path)
    except Exception as exc:
        # Log through latex_jats so the collector picks it up and the step
        # is marked as "warnings" rather than "ok".
        logging.getLogger("latex_jats").warning(
            "Quarto PDF compilation failed (continuing without PDF): %s", exc
        )
    _finish_step(engine, doi_suffix, "compile", collector.drain(),
                 log_dirs=[workspace_dir])

    # ── Step 3: convert (render JATS + post-processing + zip) ────────
    step_tracker[0] = "convert"
    _start_step(engine, doi_suffix, "convert")

    # Determine article ID from the qmd YAML (for validation/logging only)
    try:
        article_id = get_doi_suffix_from_qmd(workspace_qmd)
    except Exception:
        article_id = doi_suffix
    if article_id != doi_suffix:
        logger.info(
            "Article ID from QMD (%s) differs from manuscript doi_suffix (%s); "
            "output files will be named after doi_suffix",
            article_id, doi_suffix,
        )

    output_xml = convert_output / f"{doi_suffix}.xml"
    convert_quarto(workspace_qmd, output_xml, html=True, lastpage=lastpage)

    # Copy PDF to convert output for web preview
    if pdf_path and pdf_path.exists():
        dest_pdf = convert_output / f"{doi_suffix}.pdf"
        if dest_pdf != pdf_path:
            shutil.copy2(pdf_path, dest_pdf)

    # Create publisher zip
    zip_path = convert_output / f"{doi_suffix}.zip"
    create_publisher_zip(output_xml, pdf_path, zip_path)
    convert_log_dir = convert_output / "logs"
    _finish_step(engine, doi_suffix, "convert", collector.drain(),
                 log_dirs=[convert_log_dir])

    # ── Step 4: compare metadata against OJS ────────────────────────
    step_tracker[0] = "check"
    _start_step(engine, doi_suffix, "check")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        if ms and ms.ojs_submission_id:
            ms_authors = session.exec(
                select(ManuscriptAuthor)
                .where(ManuscriptAuthor.manuscript_id == doi_suffix)
                .order_by(ManuscriptAuthor.order)
            ).all()
            compare_metadata(
                output_xml, ms, ms_authors,
                output_json=convert_output / "metadata_comparison.json",
            )
    _finish_step(engine, doi_suffix, "check", collector.drain())

    # ── Step 5: validate JATS XML ────────────────────────────────────
    step_tracker[0] = "validate"
    _start_step(engine, doi_suffix, "validate")
    validate_jats(str(output_xml))
    _finish_step(engine, doi_suffix, "validate", collector.drain())

    # ── Done ─────────────────────────────────────────────────────────
    step_tracker[0] = ""
    _update_manuscript(
        engine,
        doi_suffix,
        status=ManuscriptStatus.ready,
        job_completed_at=datetime.utcnow(),
    )


def run_pipeline(
    doi_suffix: str, engine: Engine, storage: Storage, *,
    fix: bool = False, use_canonical_ccr_cls: bool = False,
) -> None:
    """Execute the full conversion pipeline for a manuscript.

    This function is intended to run as a FastAPI background task.  It creates
    its own DB sessions (the request session is already closed by the time a
    background task runs).

    Automatically detects whether the uploaded source is Quarto (.qmd) or
    LaTeX (.tex) and delegates to the appropriate pipeline.
    """
    collector = _LogCollector()
    pipeline_logger = logging.getLogger("latex_jats")
    pipeline_logger.addHandler(collector)
    # Ensure the logger passes INFO+ records to our handler even if the root
    # logger is configured at a higher level (e.g. WARNING in test/production).
    prev_level = pipeline_logger.level
    if pipeline_logger.level > logging.INFO or pipeline_logger.level == logging.NOTSET:
        pipeline_logger.setLevel(logging.INFO)

    # Mutable container so sub-pipeline functions can update the current step
    # for error handling in the outer except block.
    step_tracker = ["prepare"]

    try:
        # ── Transition to processing ─────────────────────────────────────
        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.processing,
            job_started_at=datetime.utcnow(),
            job_completed_at=None,
            job_log="",
        )

        source_dir = storage.source_dir(doi_suffix)
        storage.ensure_dirs(doi_suffix)

        is_quarto = _is_quarto_source(source_dir)

        # ── Step 1: prepare ──────────────────────────────────────────────
        _start_step(engine, doi_suffix, "prepare")

        if is_quarto:
            _run_quarto_pipeline(
                doi_suffix, engine, storage, collector, step_tracker,
                use_canonical_ccr_cls=use_canonical_ccr_cls,
            )
        else:
            _run_latex_pipeline(
                doi_suffix, engine, storage, collector, step_tracker,
                fix=fix, use_canonical_ccr_cls=use_canonical_ccr_cls,
            )

    except Exception:
        tb = traceback.format_exc()
        log_text = collector.drain()
        if log_text:
            log_text += "\n"
        log_text += tb

        current_step = step_tracker[0]
        # Mark the current step as failed and remaining steps as skipped
        if current_step:
            step_log_dirs: list[Path] = []
            if current_step == "compile":
                step_log_dirs = [storage.prepare_output_dir(doi_suffix)]
            elif current_step == "convert":
                step_log_dirs = [storage.convert_output_dir(doi_suffix) / "logs"]
            _finish_step(engine, doi_suffix, current_step, log_text,
                         failed=True, log_dirs=step_log_dirs or None)
            remaining = PIPELINE_STEPS[PIPELINE_STEPS.index(current_step) + 1:]
            _skip_remaining_steps(engine, doi_suffix, remaining)
        else:
            _append_log(engine, doi_suffix, log_text)

        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.failed,
            job_completed_at=datetime.utcnow(),
        )

    finally:
        pipeline_logger.removeHandler(collector)
        pipeline_logger.setLevel(prev_level)
