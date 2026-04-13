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
from web.backend.app.models import AccessToken, Manuscript  # noqa: F401
from web.backend.app.storage import Storage


@pytest.fixture
def test_storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path)


@pytest.fixture
def client(tmp_path: Path, test_storage: Storage):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

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


# ── Manuscript CRUD ───────────────────────────────────────────────────────────


def test_create_manuscript(client):
    r = client.post(
        "/api/manuscripts",
        json={"title": "Test Article", "doi_suffix": "CCR2025.1.1.TEST"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["doi_suffix"] == "CCR2025.1.1.TEST"
    assert data["title"] == "Test Article"
    assert data["status"] == "draft"
    assert data["uploaded_at"] is None
    assert data["job_log"] == ""
    assert data["job_started_at"] is None
    assert data["job_completed_at"] is None


def test_create_manuscript_duplicate(client):
    payload = {"title": "Test Article", "doi_suffix": "CCR2025.1.1.TEST"}
    client.post("/api/manuscripts", json=payload)
    r = client.post("/api/manuscripts", json=payload)
    assert r.status_code == 409


def test_list_manuscripts(client):
    client.post("/api/manuscripts", json={"title": "A", "doi_suffix": "CCR2025.1.1.AAA"})
    client.post("/api/manuscripts", json={"title": "B", "doi_suffix": "CCR2025.1.1.BBB"})
    r = client.get("/api/manuscripts")
    assert r.status_code == 200
    doi_suffixes = [m["doi_suffix"] for m in r.json()]
    assert "CCR2025.1.1.AAA" in doi_suffixes
    assert "CCR2025.1.1.BBB" in doi_suffixes


def test_get_manuscript(client):
    client.post("/api/manuscripts", json={"title": "A", "doi_suffix": "CCR2025.1.1.AAA"})
    r = client.get("/api/manuscripts/CCR2025.1.1.AAA")
    assert r.status_code == 200
    assert r.json()["doi_suffix"] == "CCR2025.1.1.AAA"


def test_get_manuscript_not_found(client):
    r = client.get("/api/manuscripts/DOES-NOT-EXIST")
    assert r.status_code == 404


# ── Upload ────────────────────────────────────────────────────────────────────


def _create(client, doi_suffix="CCR2025.1.1.TEST"):
    client.post("/api/manuscripts", json={"title": "T", "doi_suffix": doi_suffix})
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
    assert data["status"] == "queued"
    assert data["doi_suffix"] == doi
    assert (test_storage.source_dir(doi) / "main.tex").exists()
    mock_pipeline.assert_called_once()


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
    assert r.json()["status"] == "queued"

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


@patch("web.backend.app.routes.upload.run_pipeline")
def test_status_queued(mock_pipeline, client):
    doi = _create(client)
    client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["job_log"] == ""


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
    client.post("/api/manuscripts", json={"title": "Integration Test", "doi_suffix": doi})

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

    # Check status — pipeline should have completed
    r = client.get(f"/api/manuscripts/{doi}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready", f"Expected ready, got {data['status']}. Log:\n{data['job_log']}"
    assert data["job_log"] != ""
    assert data["job_started_at"] is not None
    assert data["job_completed_at"] is not None

    # Download the zip
    r = client.get(f"/api/manuscripts/{doi}/download")
    assert r.status_code == 200
    assert "application/zip" in r.headers.get("content-type", "")
    assert len(r.content) > 0
