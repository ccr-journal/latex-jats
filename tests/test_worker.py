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
from web.backend.app.worker import init_pipeline_steps, run_pipeline


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


def _create_manuscript(engine, doi_suffix="CCR2025.1.1.TEST", *, init_steps=False) -> str:
    with Session(engine) as session:
        ms = Manuscript(
            doi_suffix=doi_suffix,
            title="Test",
            status=ManuscriptStatus.queued,
            pipeline_steps=init_pipeline_steps() if init_steps else None,
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


# ── Manifest writer ──────────────────────────────────────────────────────────


_FAKE_TOOL_VERSIONS = {
    "tex_engine": "xelatex",
    "tex_version": "XeTeX 3.141592653 (fake)",
    "biber": "biber 2.20",
    "latexmlc": "0.8.8",
}


@patch(f"{_WORKER_MODULE}._capture_tool_versions", return_value=_FAKE_TOOL_VERSIONS)
@patch(f"{_WORKER_MODULE}.create_publisher_zip")
@patch(f"{_WORKER_MODULE}.convert")
@patch(f"{_WORKER_MODULE}.preprocess_for_latexml")
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=True)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
@patch(f"{_WORKER_MODULE}.get_doi_suffix", return_value="CCR2025.1.1.TEST")
def test_manifest_written_on_success(
    mock_doi, mock_prepare, mock_compile, mock_preprocess,
    mock_convert, mock_zip, mock_versions, engine, storage,
):
    import json

    doi = _create_manuscript(engine, init_steps=True)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"
    # Need a source_dir so _is_quarto_source can resolve
    storage.source_dir(doi).mkdir(parents=True, exist_ok=True)
    (storage.source_dir(doi) / "main.tex").write_text("\\documentclass{article}")

    run_pipeline(doi, engine, storage, fix=True, use_canonical_ccr_cls=False)

    manifest_path = storage.manifest_path(doi)
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["doi_suffix"] == doi
    assert manifest["pipeline"] == "latex"
    assert manifest["pipeline_config"] == {
        "fix": True, "use_canonical_ccr_cls": False,
    }
    assert manifest["tool_versions"] == _FAKE_TOOL_VERSIONS
    assert manifest["run"]["final_status"] == ManuscriptStatus.ready.value
    assert manifest["run"]["started_at"] is not None
    assert manifest["run"]["completed_at"] is not None
    # Step list reflects the five pipeline phases
    step_names = [s["name"] for s in manifest["pipeline_steps"]]
    assert step_names == ["prepare", "compile", "convert", "check", "validate"]


@patch(f"{_WORKER_MODULE}._capture_tool_versions", return_value=_FAKE_TOOL_VERSIONS)
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=False)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
def test_manifest_written_on_failure(
    mock_prepare, mock_compile, mock_versions, engine, storage,
):
    """A failed run still gets a manifest — useful for bug forensics."""
    import json

    doi = _create_manuscript(engine, init_steps=True)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"
    storage.source_dir(doi).mkdir(parents=True, exist_ok=True)
    (storage.source_dir(doi) / "main.tex").write_text("\\documentclass{article}")

    run_pipeline(doi, engine, storage)

    manifest_path = storage.manifest_path(doi)
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["run"]["final_status"] == ManuscriptStatus.failed.value


@patch(f"{_WORKER_MODULE}._capture_tool_versions", return_value=_FAKE_TOOL_VERSIONS)
@patch(f"{_WORKER_MODULE}.create_publisher_zip")
@patch(f"{_WORKER_MODULE}.convert")
@patch(f"{_WORKER_MODULE}.preprocess_for_latexml")
@patch(f"{_WORKER_MODULE}.compile_latex", return_value=True)
@patch(f"{_WORKER_MODULE}.prepare_workspace")
@patch(f"{_WORKER_MODULE}.get_doi_suffix", return_value="CCR2025.1.1.TEST")
def test_manifest_captures_per_step_warnings(
    mock_doi, mock_prepare, mock_compile, mock_preprocess,
    mock_convert, mock_zip, mock_versions, engine, storage,
):
    """Warnings emitted during a step should land in that step's manifest log."""
    import json
    import logging

    doi = _create_manuscript(engine, init_steps=True)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    storage.source_dir(doi).mkdir(parents=True, exist_ok=True)
    (storage.source_dir(doi) / "main.tex").write_text("\\documentclass{article}")

    def fake_prepare(*args, **kwargs):
        logging.getLogger("jatsmith.prepare_source").warning(
            "Found bare > in text mode at line 42"
        )
        return workspace_dir / "main.tex"

    mock_prepare.side_effect = fake_prepare

    run_pipeline(doi, engine, storage)

    manifest = json.loads(storage.manifest_path(doi).read_text())
    steps_by_name = {s["name"]: s for s in manifest["pipeline_steps"]}
    # The warning was emitted during prepare → captured under that step,
    # and the status reflects warnings (not just "ok").
    assert "bare > in text mode" in (steps_by_name["prepare"]["log"] or "")
    assert steps_by_name["prepare"]["status"] == "warnings"
    # compile_latex was mocked with no side effects → no captured log,
    # null rather than the "(no warnings or errors)" UI placeholder.
    assert steps_by_name["compile"]["log"] is None


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
    """Pipeline log messages from the jatsmith logger should be captured in job_log."""
    import logging

    doi = _create_manuscript(engine)
    workspace_dir = storage.prepare_output_dir(doi)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.tex").write_text("\\documentclass{article}")
    mock_prepare.return_value = workspace_dir / "main.tex"

    # Make prepare_workspace emit a log message
    def fake_prepare(*args, **kwargs):
        logging.getLogger("jatsmith.prepare_source").info("Preparing workspace...")
        return workspace_dir / "main.tex"

    mock_prepare.side_effect = fake_prepare

    run_pipeline(doi, engine, storage)

    ms = _get_manuscript(engine, doi)
    assert "Preparing workspace" in ms.job_log
