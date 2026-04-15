"""Unit tests for the FastAPI backend.

Uses FastAPI's TestClient with dependency overrides so that:
- get_session uses an in-memory SQLite database
- get_storage uses a tmp_path-based Storage instance

No real filesystem storage or network calls are made.
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web.backend.app import deps
from web.backend.app.main import app
from web.backend.app.models import (  # noqa: F401
    AccessToken,
    LoginState,
    Manuscript,
)
from web.backend.app.storage import Storage


EDITOR_TOKEN = "editor-test-token"
EDITOR_ORCID = "0000-0000-0000-0001"


@pytest.fixture
def test_storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def anon_client(tmp_path: Path, test_storage: Storage, engine):
    def override_session():
        with Session(engine) as session:
            yield session

    def override_storage():
        return test_storage

    app.dependency_overrides[deps.get_session] = override_session
    app.dependency_overrides[deps.get_storage] = override_storage
    deps._engine = engine
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    deps._engine = None


@pytest.fixture
def client(anon_client: TestClient, engine):
    with Session(engine) as session:
        session.add(
            AccessToken(
                token=EDITOR_TOKEN,
                orcid=EDITOR_ORCID,
                name="Test Editor",
            )
        )
        session.commit()
    anon_client.headers.update({"Authorization": f"Bearer {EDITOR_TOKEN}"})
    return anon_client


# ── Auth negatives ────────────────────────────────────────────────────────────


def test_manuscripts_require_auth(anon_client):
    assert anon_client.get("/api/manuscripts").status_code == 401
    r = anon_client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.X"})
    assert r.status_code == 401


def test_bad_bearer_token(anon_client):
    anon_client.headers.update({"Authorization": "Bearer nonsense"})
    assert anon_client.get("/api/manuscripts").status_code == 401


# ── Manuscript CRUD ───────────────────────────────────────────────────────────


def test_create_manuscript(client):
    r = client.post(
        "/api/manuscripts",
        json={"doi_suffix": "CCR2025.1.1.TEST"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["doi_suffix"] == "CCR2025.1.1.TEST"
    assert data["status"] == "draft"
    assert data["uploaded_at"] is None
    assert data["job_log"] == ""
    assert data["job_started_at"] is None
    assert data["job_completed_at"] is None
    assert data["pipeline_steps"] is None


def test_create_manuscript_duplicate(client):
    payload = {"doi_suffix": "CCR2025.1.1.TEST"}
    client.post("/api/manuscripts", json=payload)
    r = client.post("/api/manuscripts", json=payload)
    assert r.status_code == 409


def test_list_manuscripts(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.AAA"})
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.BBB"})
    r = client.get("/api/manuscripts")
    assert r.status_code == 200
    doi_suffixes = [m["doi_suffix"] for m in r.json()]
    assert "CCR2025.1.1.AAA" in doi_suffixes
    assert "CCR2025.1.1.BBB" in doi_suffixes


def test_get_manuscript(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.AAA"})
    r = client.get("/api/manuscripts/CCR2025.1.1.AAA")
    assert r.status_code == 200
    assert r.json()["doi_suffix"] == "CCR2025.1.1.AAA"


def test_get_manuscript_not_found(client):
    r = client.get("/api/manuscripts/DOES-NOT-EXIST")
    assert r.status_code == 404


# ── Upload ────────────────────────────────────────────────────────────────────


def _create(client, doi_suffix="CCR2025.1.1.TEST"):
    client.post("/api/manuscripts", json={"doi_suffix": doi_suffix})
    return doi_suffix


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_single_file(mock_pipeline, client, test_storage):
    doi = _create(client)
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"\\documentclass{article}", "text/plain"))],
        data={"uploaded_by": "editor"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "uploaded"
    assert data["doi_suffix"] == doi
    assert (test_storage.source_dir(doi) / "main.tex").exists()
    # Upload no longer auto-starts the pipeline
    mock_pipeline.assert_not_called()


@patch("web.backend.app.routes.upload.run_pipeline")
def test_process_starts_pipeline(mock_pipeline, client, test_storage):
    """POST /process should kick off the pipeline after upload."""
    doi = _create(client)
    client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    r = client.post(f"/api/manuscripts/{doi}/process", data={"fix": "false"})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    mock_pipeline.assert_called_once()


def test_process_without_upload_rejected(client):
    doi = _create(client)
    r = client.post(f"/api/manuscripts/{doi}/process")
    assert r.status_code == 400


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_zip(mock_pipeline, client, test_storage):
    doi = _create(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.tex", "\\documentclass{article}")
        zf.writestr("figures/fig1.pdf", b"\x00\x01\x02")
    buf.seek(0)
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("source.zip", buf.read(), "application/zip"))],
        data={"uploaded_by": "author"},
    )
    assert r.status_code == 201
    assert (test_storage.source_dir(doi) / "main.tex").exists()
    assert (test_storage.source_dir(doi) / "figures" / "fig1.pdf").exists()


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_zip_single_wrapper_dir(mock_pipeline, client, test_storage):
    """A zip with a single top-level directory should have that prefix stripped."""
    doi = _create(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CCR2025.1.2.YAO/main.tex", "\\documentclass{article}")
        zf.writestr("CCR2025.1.2.YAO/figures/fig1.pdf", b"\x00\x01\x02")
    buf.seek(0)
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("source.zip", buf.read(), "application/zip"))],
    )
    assert r.status_code == 201
    assert (test_storage.source_dir(doi) / "main.tex").exists()
    assert (test_storage.source_dir(doi) / "figures" / "fig1.pdf").exists()
    # The wrapper directory itself should not appear
    assert not (test_storage.source_dir(doi) / "CCR2025.1.2.YAO").exists()


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_zip_slip(mock_pipeline, client, test_storage):
    """A zip with a path-traversal entry must not escape the source directory."""
    doi = _create(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escaped.txt", "evil")
        zf.writestr("safe.tex", "safe")
    buf.seek(0)
    client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("source.zip", buf.read(), "application/zip"))],
    )
    source_dir = test_storage.source_dir(doi)
    assert not (source_dir.parent / "escaped.txt").exists()
    assert (source_dir / "safe.tex").exists()


def test_upload_not_found(client):
    r = client.post(
        "/api/manuscripts/DOES-NOT-EXIST/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    assert r.status_code == 404


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_rejected_while_processing(mock_pipeline, client):
    """Upload should be rejected if a conversion is already in progress."""
    doi = _create(client)
    # First upload succeeds
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    assert r.status_code == 201
    assert r.json()["status"] == "uploaded"

    # Kick off processing (status becomes queued via background task)
    client.post(f"/api/manuscripts/{doi}/process")

    # Second upload while queued should be rejected
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"y", "text/plain"))],
    )
    assert r.status_code == 409


# ── Status ────────────────────────────────────────────────────────────────────


def test_status_draft(client):
    doi = _create(client)
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "draft"
    assert data["job_log"] == ""
    assert data["job_started_at"] is None
    assert data["pipeline_steps"] is None


@patch("web.backend.app.routes.upload.run_pipeline")
def test_status_after_upload(mock_pipeline, client):
    doi = _create(client)
    client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "uploaded"
    assert data["job_log"] == ""
    # pipeline_steps is cleared on upload; set when processing starts
    assert data["pipeline_steps"] is None


@patch("web.backend.app.routes.upload.run_pipeline")
def test_status_queued(mock_pipeline, client):
    doi = _create(client)
    client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    client.post(f"/api/manuscripts/{doi}/process")
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    # pipeline_steps should be initialized with all-pending steps
    steps = data["pipeline_steps"]
    assert steps is not None
    assert len(steps) == 4
    assert all(s["status"] == "pending" for s in steps)


def test_status_not_found(client):
    r = client.get("/api/manuscripts/DOES-NOT-EXIST/status")
    assert r.status_code == 404


# ── Download ──────────────────────────────────────────────────────────────────


def test_download_not_ready(client):
    doi = _create(client)
    r = client.get(f"/api/manuscripts/{doi}/download")
    assert r.status_code == 404


def test_download_not_found(client):
    r = client.get("/api/manuscripts/DOES-NOT-EXIST/download")
    assert r.status_code == 404


# ── Output file serving ──────────────────────────────────────────────────────


def test_output_file(client, test_storage):
    doi = _create(client)
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "test.html").write_text("<html>proof</html>")

    r = client.get(f"/api/manuscripts/{doi}/output/test.html")
    assert r.status_code == 200
    assert "proof" in r.text


def test_output_file_not_found(client):
    doi = _create(client)
    r = client.get(f"/api/manuscripts/{doi}/output/nonexistent.html")
    assert r.status_code == 404


def test_output_file_manuscript_not_found(client):
    r = client.get("/api/manuscripts/DOES-NOT-EXIST/output/test.html")
    assert r.status_code == 404


def test_output_file_path_traversal(client, test_storage):
    """Path traversal attempts must not escape the output directory."""
    doi = _create(client)
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Write a file outside the output dir
    (output_dir.parent / "secret.txt").write_text("secret")

    r = client.get(f"/api/manuscripts/{doi}/output/../secret.txt")
    assert r.status_code == 404


# ── classify_step_status ─────────────────────────────────────────────────────

from web.backend.app.worker import classify_step_status


def test_classify_step_status_ok():
    assert classify_step_status("INFO: all good\nINFO: done") == "ok"
    assert classify_step_status("") == "ok"


def test_classify_step_status_warnings():
    assert classify_step_status("WARNING: something\nINFO: done") == "warnings"


def test_classify_step_status_errors():
    assert classify_step_status("ERROR: bad thing") == "errors"
    assert classify_step_status("WARNING: LaTeXML: Error: foo") == "errors"


def test_classify_step_status_errors_over_warnings():
    assert classify_step_status("WARNING: minor\nERROR: critical") == "errors"


# ── Integration: full upload → convert → download ────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "latex"


@pytest.mark.integration
def test_upload_convert_download(client, test_storage):
    """Full pipeline: upload LaTeX source, run conversion, download zip.

    Requires latexmlc (and pdflatex/biber for compilation). The TestClient
    runs BackgroundTasks synchronously, so the pipeline completes within the
    upload request.
    """
    # The authors.tex fixture has \doi{10.0000/test}, so get_doi_suffix returns "test"
    doi = "test"
    client.post("/api/manuscripts", json={"doi_suffix": doi})

    # Upload the fixture files
    fixture_files = ["authors.tex", "ccr.cls", "bibliography.bib"]
    files = []
    for name in fixture_files:
        content = (FIXTURES / name).read_bytes()
        # authors.tex must be uploaded as main.tex (pipeline expects main.tex)
        upload_name = "main.tex" if name == "authors.tex" else name
        files.append(("files", (upload_name, content, "application/octet-stream")))

    r = client.post(f"/api/manuscripts/{doi}/upload", files=files)
    assert r.status_code == 201

    # Start the pipeline (upload no longer does it automatically)
    r = client.post(f"/api/manuscripts/{doi}/process")
    assert r.status_code == 200

    # Check status — pipeline should have completed
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready", f"Expected ready, got {data['status']}. Log:\n{data['job_log']}"
    assert data["job_log"] != ""
    assert data["job_started_at"] is not None
    assert data["job_completed_at"] is not None

    # Check pipeline steps
    steps = data["pipeline_steps"]
    assert steps is not None
    assert len(steps) == 4
    assert [s["name"] for s in steps] == ["prepare", "compile", "convert", "validate"]
    for step in steps:
        assert step["status"] not in ("pending", "running"), f"Step {step['name']} still {step['status']}"
        assert step["started_at"] is not None
        assert step["completed_at"] is not None
        assert isinstance(step["logs"], list)

    # Download the zip
    r = client.get(f"/api/manuscripts/{doi}/download")
    assert r.status_code == 200
    assert "application/zip" in r.headers.get("content-type", "")
    assert len(r.content) > 0
