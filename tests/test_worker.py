"""Unit tests for the background pipeline worker.

Mocks all pipeline functions (prepare_workspace, compile_latex, convert, etc.)
so these tests run without a LaTeX toolchain.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web.backend.app.models import Manuscript, ManuscriptStatus
from web.backend.app.storage import Storage
from web.backend.app.worker import run_pipeline


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(e)
    return e


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path)


def _create_manuscript(engine, doi_suffix="CCR2025.1.1.TEST") -> str:
    with Session(engine) as session:
        ms = Manuscript(
            doi_suffix=doi_suffix,
            title="Test",
            status=ManuscriptStatus.queued,
        )
        session.add(ms)
        session.commit()
    return doi_suffix


def _get_manuscript(engine, doi_suffix) -> Manuscript:
    with Session(engine) as session:
        ms = session.get(Manuscript, doi_suffix)
        # Detach from session so we can read fields after close
        session.expunge(ms)
        return ms


_WORKER_MODULE = "web.backend.app.worker"


@patch(f"{_WORKER_MODULE}.create_publisher_zip")
@patch(f"{_WORKER_MODULE}.convert")
@patch(f"{_WORKER_MODULE}.preprocess_for_latexml")
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=True)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
@patch(f"{_WORKER_MODULE}.get_doi_suffix", return_value="CCR2025.1.1.TEST")
def test_happy_path(
    mock_doi, mock_prepare, mock_compile, mock_preprocess,
    mock_convert, mock_zip, engine, storage,
):
    doi = _create_manuscript(engine)
    # prepare_workspace needs to return a Path to main.tex
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"

    run_pipeline(doi, engine, storage)

    ms = _get_manuscript(engine, doi)
    assert ms.status == ManuscriptStatus.ready
    assert ms.job_started_at is not None
    assert ms.job_completed_at is not None

    mock_prepare.assert_called_once()
    mock_compile.assert_called_once()
    mock_preprocess.assert_called_once()
    mock_convert.assert_called_once()
    mock_zip.assert_called_once()


@patch(f"{_WORKER_MODULE}.compile_latex", return_value=False)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
def test_compile_failure(mock_prepare, mock_compile, engine, storage):
    doi = _create_manuscript(engine)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"

    run_pipeline(doi, engine, storage)

    ms = _get_manuscript(engine, doi)
    assert ms.status == ManuscriptStatus.failed
    assert ms.job_started_at is not None
    assert ms.job_completed_at is not None


@patch(f"{_WORKER_MODULE}.preprocess_for_latexml")
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=True)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
@patch(f"{_WORKER_MODULE}.get_doi_suffix", return_value="CCR2025.1.1.TEST")
def test_convert_exception(
    mock_doi, mock_prepare, mock_compile, mock_preprocess, engine, storage,
):
    """An exception during convert() should set status=failed with traceback in log."""
    doi = _create_manuscript(engine)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"

    # Make convert() blow up — patch it inside the function's import scope
    with patch(f"{_WORKER_MODULE}.convert", side_effect=RuntimeError("boom")):
        run_pipeline(doi, engine, storage)

    ms = _get_manuscript(engine, doi)
    assert ms.status == ManuscriptStatus.failed
    assert "boom" in ms.job_log
    assert ms.job_completed_at is not None


@patch(f"{_WORKER_MODULE}.create_publisher_zip")
@patch(f"{_WORKER_MODULE}.convert")
@patch(f"{_WORKER_MODULE}.preprocess_for_latexml")
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=True)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
@patch(f"{_WORKER_MODULE}.get_doi_suffix", return_value="CCR2025.1.1.TEST")
def test_log_capture(
    mock_doi, mock_prepare, mock_compile, mock_preprocess,
    mock_convert, mock_zip, engine, storage,
):
    """Pipeline log messages from the latex_jats logger should be captured in job_log."""
    import logging

    doi = _create_manuscript(engine)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"

    # Make prepare_workspace emit a log message
    def fake_prepare(*args, **kwargs):
        logging.getLogger("latex_jats.prepare_source").info("Preparing workspace...")
        return workspace_dir / "main.tex"

    mock_prepare.side_effect = fake_prepare

    run_pipeline(doi, engine, storage)

    ms = _get_manuscript(engine, doi)
    assert "Preparing workspace" in ms.job_log
