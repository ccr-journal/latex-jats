"""Background pipeline runner.

Called from the upload route via FastAPI BackgroundTasks.  Runs the full
prepare → compile → convert → validate pipeline and updates the Manuscript row
with status transitions and captured log output.
"""

import logging
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from latex_jats.convert import (
    convert,
    create_publisher_zip,
    get_doi_suffix,
    preprocess_for_latexml,
    validate_jats,
)
from latex_jats.prepare_source import compile_latex, prepare_workspace

from .models import Manuscript, ManuscriptStatus, PIPELINE_STEPS, StepStatus
from .storage import Storage

logger = logging.getLogger(__name__)


class _LogCollector(logging.Handler):
    """Collects log records from the ``latex_jats`` logger hierarchy."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.buffer: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
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


def _finish_step(engine: Engine, doi_suffix: str, step_name: str,
                 log_text: str, *, failed: bool = False,
                 log_dirs: list[Path] | None = None) -> None:
    """Mark a pipeline step as completed and store its logs."""
    status = StepStatus.failed if failed else classify_step_status(log_text)
    logs: list[dict] = []
    if log_text.strip():
        logs.append({"name": "pipeline", "content": log_text.strip()})
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


def run_pipeline(doi_suffix: str, engine: Engine, storage: Storage, *, fix: bool = False) -> None:
    """Execute the full conversion pipeline for a manuscript.

    This function is intended to run as a FastAPI background task.  It creates
    its own DB sessions (the request session is already closed by the time a
    background task runs).
    """
    collector = _LogCollector()
    pipeline_logger = logging.getLogger("latex_jats")
    pipeline_logger.addHandler(collector)
    # Ensure the logger passes INFO+ records to our handler even if the root
    # logger is configured at a higher level (e.g. WARNING in test/production).
    prev_level = pipeline_logger.level
    if pipeline_logger.level > logging.INFO or pipeline_logger.level == logging.NOTSET:
        pipeline_logger.setLevel(logging.INFO)

    current_step = None

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
        workspace_dir = storage.prepare_output_dir(doi_suffix)
        convert_output = storage.convert_output_dir(doi_suffix)
        storage.ensure_dirs(doi_suffix)

        # ── Step 1: prepare workspace ────────────────────────────────────
        current_step = "prepare"
        _start_step(engine, doi_suffix, "prepare")
        workspace_tex = prepare_workspace(source_dir, workspace_dir, fix_problems=fix)
        _finish_step(engine, doi_suffix, "prepare", collector.drain())

        # ── Step 2: compile LaTeX ────────────────────────────────────────
        current_step = "compile"
        _start_step(engine, doi_suffix, "compile")
        log_dir = storage.prepare_output_dir(doi_suffix)
        ok = compile_latex(workspace_dir, log_dir=log_dir)
        _finish_step(engine, doi_suffix, "compile", collector.drain(),
                     failed=not ok, log_dirs=[log_dir])

        if not ok:
            _skip_remaining_steps(engine, doi_suffix, ["convert", "validate"])
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
        current_step = "convert"
        _start_step(engine, doi_suffix, "convert")
        preprocess_for_latexml(workspace_dir)

        # Determine article ID from the LaTeX preamble
        try:
            article_id = get_doi_suffix(workspace_tex)
        except Exception:
            article_id = doi_suffix

        output_xml = convert_output / f"{article_id}.xml"

        lastpage = None
        if pdf_src.exists():
            lastpage = _pdf_page_count(pdf_src)

        convert(workspace_tex, output_xml, html=True, lastpage=lastpage)

        # Copy PDF to convert output for web preview
        pdf_path = source_dir / "main.pdf" if (source_dir / "main.pdf").exists() else None
        if pdf_path:
            shutil.copy2(pdf_path, convert_output / f"{article_id}.pdf")

        # Create publisher zip
        zip_path = convert_output / f"{article_id}.zip"
        create_publisher_zip(output_xml, pdf_path, zip_path)
        convert_log_dir = convert_output / "logs"
        _finish_step(engine, doi_suffix, "convert", collector.drain(),
                     log_dirs=[convert_log_dir])

        # ── Step 4: validate JATS XML ────────────────────────────────────
        current_step = "validate"
        _start_step(engine, doi_suffix, "validate")
        validate_jats(str(output_xml))
        _finish_step(engine, doi_suffix, "validate", collector.drain())

        # ── Done ─────────────────────────────────────────────────────────
        current_step = None
        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.ready,
            job_completed_at=datetime.utcnow(),
        )

    except Exception:
        tb = traceback.format_exc()
        log_text = collector.drain()
        if log_text:
            log_text += "\n"
        log_text += tb

        # Mark the current step as failed and remaining steps as skipped
        if current_step:
            _finish_step(engine, doi_suffix, current_step, log_text, failed=True)
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
