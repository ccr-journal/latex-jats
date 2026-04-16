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

from web.backend.app import deps, ojs as ojs_client
from web.backend.app.main import app
from web.backend.app.models import (  # noqa: F401
    AccessToken,
    LoginState,
    Manuscript,
    ManuscriptAuthor,
)
from web.backend.app.storage import Storage


EDITOR_TOKEN = "editor-test-token"
EDITOR_ORCID = "0000-0000-0000-0001"
AUTHOR_TOKEN = "author-test-token"
AUTHOR_ORCID = "0000-0000-0000-0002"
OTHER_ORCID = "0000-0000-0000-0003"


@pytest.fixture(autouse=True)
def _editor_orcid_override(monkeypatch):
    """Pin the editor ORCID set so get_current_role doesn't hit the network."""
    async def fake_fetch(cfg=None):
        return frozenset({EDITOR_ORCID})
    monkeypatch.setattr(ojs_client, "fetch_editor_orcids", fake_fetch)
    yield
    ojs_client.set_production_submissions_override(None)


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
        session.add(
            AccessToken(
                token=AUTHOR_TOKEN,
                orcid=AUTHOR_ORCID,
                name="Test Author",
            )
        )
        session.commit()
    anon_client.headers.update({"Authorization": f"Bearer {EDITOR_TOKEN}"})
    return anon_client


@pytest.fixture
def author_client(client: TestClient):
    """Separate client sharing the same engine/overrides, authed as non-editor.

    Must be used alongside `client` — both point at the same FastAPI app and
    dependency overrides, so requests through either see the same database.
    """
    from fastapi.testclient import TestClient as _TC
    ac = _TC(app, raise_server_exceptions=False)
    ac.headers.update({"Authorization": f"Bearer {AUTHOR_TOKEN}"})
    return ac


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


# ── Presigned URLs ───────────────────────────────────────────────────────────


def test_presign_returns_token(client):
    doi = _create(client)
    r = client.get(f"/api/manuscripts/{doi}/presign")
    assert r.status_code == 200
    assert "token" in r.json()


def test_presign_requires_auth(client):
    doi = _create(client)
    r = client.get(
        f"/api/manuscripts/{doi}/presign",
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


def test_output_file_with_presign_token(client, test_storage):
    doi = _create(client)
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "test.html").write_text("<html>proof</html>")

    # Get presign token
    token = client.get(f"/api/manuscripts/{doi}/presign").json()["token"]

    # Access output without Authorization header, using presign token
    r = client.get(
        f"/api/manuscripts/{doi}/output/test.html",
        params={"token": token},
        headers={"Authorization": ""},  # clear the default auth
    )
    assert r.status_code == 200
    assert "proof" in r.text


def test_output_file_with_invalid_presign_token(client, test_storage):
    doi = _create(client)
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "test.html").write_text("<html>proof</html>")

    r = client.get(
        f"/api/manuscripts/{doi}/output/test.html",
        params={"token": "invalid-token"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


def test_presign_token_scoped_to_manuscript(client, test_storage):
    """A presign token for manuscript A must not grant access to manuscript B."""
    doi_a = _create(client, "CCR2025.1.1.AAA")
    doi_b = _create(client, "CCR2025.1.1.BBB")
    output_dir = test_storage.convert_output_dir(doi_b)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "test.html").write_text("<html>secret</html>")

    token_a = client.get(f"/api/manuscripts/{doi_a}/presign").json()["token"]

    r = client.get(
        f"/api/manuscripts/{doi_b}/output/test.html",
        params={"token": token_a},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


def test_download_with_presign_token(client, test_storage):
    doi = _create(client)
    # Create a fake zip
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{doi}.zip"
    zip_path.write_bytes(b"PK fake zip")

    token = client.get(f"/api/manuscripts/{doi}/presign").json()["token"]

    r = client.get(
        f"/api/manuscripts/{doi}/download",
        params={"token": token},
        headers={"Authorization": ""},
    )
    assert r.status_code == 200


def test_presign_sets_cookie_for_subresources(client, test_storage):
    """First request with ?token= should set a cookie for subsequent requests."""
    doi = _create(client)
    output_dir = test_storage.convert_output_dir(doi)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proof.html").write_text("<html>proof</html>")
    (output_dir / "style.css").write_text("body{}")

    token = client.get(f"/api/manuscripts/{doi}/presign").json()["token"]

    # First request sets the cookie
    r1 = client.get(
        f"/api/manuscripts/{doi}/output/proof.html",
        params={"token": token},
        headers={"Authorization": ""},
    )
    assert r1.status_code == 200
    assert "presign_token" in r1.cookies

    # Subsequent request uses only the cookie (no token param, no Authorization)
    r2 = client.get(
        f"/api/manuscripts/{doi}/output/style.css",
        headers={"Authorization": ""},
        cookies={"presign_token": r1.cookies["presign_token"]},
    )
    assert r2.status_code == 200
    assert "body{}" in r2.text


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


# ── Author access control ────────────────────────────────────────────────────


def _link_author(engine, doi: str, orcid: str) -> None:
    with Session(engine) as session:
        session.add(ManuscriptAuthor(manuscript_id=doi, orcid=orcid, order=0))
        session.commit()


def test_me_role_editor(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "editor"


def test_me_role_author(author_client):
    r = author_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "author"


def test_author_sees_only_own_manuscripts(client, author_client, engine):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.A"})
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    _link_author(engine, "CCR.A", AUTHOR_ORCID)

    r = author_client.get("/api/manuscripts")
    assert r.status_code == 200
    suffixes = [m["doi_suffix"] for m in r.json()]
    assert suffixes == ["CCR.A"]


def test_author_get_linked_manuscript(client, author_client, engine):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.A"})
    _link_author(engine, "CCR.A", AUTHOR_ORCID)
    r = author_client.get("/api/manuscripts/CCR.A")
    assert r.status_code == 200


def test_author_get_unlinked_manuscript_404(client, author_client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    r = author_client.get("/api/manuscripts/CCR.B")
    assert r.status_code == 404


def test_author_cannot_create_manuscript(author_client):
    r = author_client.post("/api/manuscripts", json={"doi_suffix": "CCR.X"})
    assert r.status_code == 403


def test_editor_sees_all(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.A"})
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    r = client.get("/api/manuscripts")
    assert {m["doi_suffix"] for m in r.json()} == {"CCR.A", "CCR.B"}


def test_author_status_of_unlinked_is_404(client, author_client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    r = author_client.get("/api/manuscripts/CCR.B/status")
    assert r.status_code == 404


@patch("web.backend.app.routes.upload.run_pipeline")
def test_author_can_upload_to_linked_manuscript(mock_pipeline, client, author_client, engine, test_storage):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.A"})
    _link_author(engine, "CCR.A", AUTHOR_ORCID)
    r = author_client.post(
        "/api/manuscripts/CCR.A/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    assert r.status_code == 201
    assert r.json()["uploaded_by"] == "author"


def test_author_cannot_upload_to_unlinked(client, author_client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    r = author_client.post(
        "/api/manuscripts/CCR.B/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    assert r.status_code == 404


# ── OJS import ────────────────────────────────────────────────────────────────


def _set_ojs_subs(submissions):
    ojs_client.set_production_submissions_override(submissions)


def test_list_ojs_submissions_editor(client):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Something",
            authors=(ojs_client.OjsAuthor(orcid=AUTHOR_ORCID, name="A Author"),),
        )
    ])
    r = client.get("/api/ojs/submissions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["submission_id"] == 42
    assert body[0]["already_imported"] is False


def test_list_ojs_submissions_forbidden_for_authors(author_client):
    r = author_client.get("/api/ojs/submissions")
    assert r.status_code == 403


def test_import_ojs_submission_creates_authors(client, engine):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Something",
            authors=(
                ojs_client.OjsAuthor(orcid=AUTHOR_ORCID, name="A Author", order=0),
                ojs_client.OjsAuthor(orcid=OTHER_ORCID, name="Other", order=1),
            ),
        )
    ])
    r = client.post("/api/ojs/submissions/42/import")
    assert r.status_code == 201
    assert r.json()["doi_suffix"] == "CCR2025.1.3.Z"
    assert r.json()["ojs_submission_id"] == 42

    with Session(engine) as session:
        from sqlmodel import select
        authors = session.exec(
            select(ManuscriptAuthor).where(
                ManuscriptAuthor.manuscript_id == "CCR2025.1.3.Z"
            )
        ).all()
    assert {a.orcid for a in authors} == {AUTHOR_ORCID, OTHER_ORCID}


def test_import_ojs_submission_duplicate(client):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Something",
            authors=(),
        )
    ])
    client.post("/api/ojs/submissions/42/import")
    r = client.post("/api/ojs/submissions/42/import")
    assert r.status_code == 409


def test_import_unknown_submission_404(client):
    _set_ojs_subs([])
    r = client.post("/api/ojs/submissions/999/import")
    assert r.status_code == 404


def test_author_cannot_import(author_client):
    r = author_client.post("/api/ojs/submissions/42/import")
    assert r.status_code == 403


def test_already_imported_flag(client):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Something",
            authors=(),
        )
    ])
    client.post("/api/ojs/submissions/42/import")
    r = client.get("/api/ojs/submissions")
    assert r.json()[0]["already_imported"] is True


# ── OJS DOI suffix extraction ─────────────────────────────────────────────────


def test_extract_doi_suffix_with_prefix():
    from web.backend.app.ojs import _extract_doi_suffix
    assert _extract_doi_suffix("10.5117/CCR2025.1.2.YAO", "10.5117/") == "CCR2025.1.2.YAO"


def test_extract_doi_suffix_fallback():
    from web.backend.app.ojs import _extract_doi_suffix
    assert _extract_doi_suffix("10.9999/CCR2025.1.2.YAO", "10.5117/") == "CCR2025.1.2.YAO"


def test_extract_doi_suffix_none():
    from web.backend.app.ojs import _extract_doi_suffix
    assert _extract_doi_suffix(None, "10.5117/") is None
    assert _extract_doi_suffix("", "10.5117/") is None


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
