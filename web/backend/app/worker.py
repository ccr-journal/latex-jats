"""Background pipeline runner.

Called from the upload route via FastAPI BackgroundTasks.  Runs the full
prepare → compile → convert → zip pipeline and updates the Manuscript row
with status transitions and captured log output.
"""

import logging
import shutil
import subprocess
import traceback
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session

from latex_jats.convert import (
    convert,
    create_publisher_zip,
    get_doi_suffix,
    preprocess_for_latexml,
)
from latex_jats.prepare_source import compile_latex, prepare_workspace

from .models import Manuscript, ManuscriptStatus
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
        workspace_tex = prepare_workspace(source_dir, workspace_dir, fix_problems=fix)
        _append_log(engine, doi_suffix, collector.drain())

        # ── Step 2: compile LaTeX ────────────────────────────────────────
        log_dir = storage.prepare_output_dir(doi_suffix)
        ok = compile_latex(workspace_dir, log_dir=log_dir)
        _append_log(engine, doi_suffix, collector.drain())

        if not ok:
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

        # ── Step 3: preprocess + convert ─────────────────────────────────
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
        _append_log(engine, doi_suffix, collector.drain())

        # Copy PDF to convert output for web preview
        pdf_path = source_dir / "main.pdf" if (source_dir / "main.pdf").exists() else None
        if pdf_path:
            shutil.copy2(pdf_path, convert_output / f"{article_id}.pdf")

        # ── Step 4: create publisher zip ─────────────────────────────────
        zip_path = convert_output / f"{article_id}.zip"
        create_publisher_zip(output_xml, pdf_path, zip_path)
        _append_log(engine, doi_suffix, collector.drain())

        # ── Done ─────────────────────────────────────────────────────────
        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.ready,
            job_completed_at=datetime.utcnow(),
        )

    except Exception:
        tb = traceback.format_exc()
        _append_log(engine, doi_suffix, collector.drain() + "\n" + tb)
        _update_manuscript(
            engine,
            doi_suffix,
            status=ManuscriptStatus.failed,
            job_completed_at=datetime.utcnow(),
        )

    finally:
        pipeline_logger.removeHandler(collector)
        pipeline_logger.setLevel(prev_level)
