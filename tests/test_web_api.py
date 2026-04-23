"""Unit tests for the FastAPI backend.

Uses FastAPI's TestClient with dependency overrides so that:
- get_session uses an in-memory SQLite database
- get_storage uses a tmp_path-based Storage instance

No real filesystem storage or network calls are made.
"""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web.backend.app import deps, ojs as ojs_client
from web.backend.app.config import AuthConfig, set_for_tests
from web.backend.app.main import app
from web.backend.app.models import (  # noqa: F401
    AccessToken,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptStatus,
    ManuscriptToken,
)
from web.backend.app.storage import Storage


EDITOR_TOKEN = "editor-test-token"
EDITOR_USERNAME = "editor"
AUTHOR_TOKEN = "author-test-token"
AUTHOR_USERNAME = "author-user"
MANUSCRIPT_TOKEN = "manuscript-access-token-12345"


TEST_CFG = AuthConfig(
    editor_credentials={EDITOR_USERNAME: "testpass", AUTHOR_USERNAME: "authorpass"},
    frontend_url="http://testserver",
    ojs_base_url="https://ojs",
    ojs_journal_path="ccr",
    ojs_admin_token="admintok",
    ojs_doi_prefix="10.5117/",
    session_token_ttl_days=30,
)


@pytest.fixture(autouse=True)
def _test_config():
    """Pin the auth config so tests don't depend on env vars."""
    set_for_tests(TEST_CFG)
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
                username=EDITOR_USERNAME,
                name="Test Editor",
            )
        )
        session.add(
            AccessToken(
                token=AUTHOR_TOKEN,
                username=AUTHOR_USERNAME,
                name="Test Author",
            )
        )
        session.commit()
    anon_client.headers.update({"Authorization": f"Bearer {EDITOR_TOKEN}"})
    return anon_client


AUTHOR_FIXTURE_DOI = "CCR.AUTHOR.FIXTURE"
AUTHOR_FIXTURE_TOKEN = "author-manuscript-token"


@pytest.fixture
def author_client(client: TestClient, engine):
    """Client authed via a per-manuscript author token (role=author).

    Sets up a fixture manuscript + ManuscriptToken so tests can assert that
    editor-only endpoints return 403 for non-editor callers.
    """
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix=AUTHOR_FIXTURE_DOI))
        session.add(
            ManuscriptToken(
                manuscript_id=AUTHOR_FIXTURE_DOI,
                token=AUTHOR_FIXTURE_TOKEN,
            )
        )
        session.commit()
    ac = TestClient(app, raise_server_exceptions=False)
    ac.headers.update({"Authorization": f"Bearer {AUTHOR_FIXTURE_TOKEN}"})
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


@patch("web.backend.app.routes.upload.run_pipeline")
def test_upload_replaces_previous_source(mock_pipeline, client, test_storage):
    """A new upload must wipe any leftover files from the previous upload
    (or pipeline artifacts written back into source_dir)."""
    doi = _create(client)
    source_dir = test_storage.source_dir(doi)

    # First upload: two files
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[
            ("files", ("main.tex", b"v1", "text/plain")),
            ("files", ("bibliography.bib", b"@x{y}", "text/plain")),
        ],
    )
    assert r.status_code == 201
    assert (source_dir / "main.tex").exists()
    assert (source_dir / "bibliography.bib").exists()

    # Simulate a pipeline artifact left behind in source_dir
    (source_dir / "main.pdf").write_bytes(b"%PDF-1.4")
    (source_dir / ".vdoc.abc.r").write_text("stale")

    # Second upload: only one file — the old ones must be gone
    r = client.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"v2", "text/plain"))],
    )
    assert r.status_code == 201
    assert (source_dir / "main.tex").read_bytes() == b"v2"
    assert not (source_dir / "bibliography.bib").exists()
    assert not (source_dir / "main.pdf").exists()
    assert not (source_dir / ".vdoc.abc.r").exists()


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
    assert len(steps) == 5
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


def _create_manuscript_token(engine, doi: str, token: str = MANUSCRIPT_TOKEN) -> None:
    with Session(engine) as session:
        session.add(ManuscriptToken(manuscript_id=doi, token=token))
        session.commit()


def test_me_role_editor(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "editor"


def test_me_role_author(author_client):
    r = author_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "author"


def test_author_cannot_create_manuscript(author_client):
    r = author_client.post("/api/manuscripts", json={"doi_suffix": "CCR.X"})
    assert r.status_code == 403


def test_editor_sees_all(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.A"})
    client.post("/api/manuscripts", json={"doi_suffix": "CCR.B"})
    r = client.get("/api/manuscripts")
    assert {m["doi_suffix"] for m in r.json()} == {"CCR.A", "CCR.B"}


# ── Manuscript token access ──────────────────────────────────────────────────


def test_manuscript_token_auth(client, engine):
    """A manuscript token grants access to its scoped manuscript."""
    doi = _create(client)
    _create_manuscript_token(engine, doi)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.get(f"/api/manuscripts/{doi}")
    assert r.status_code == 200
    assert r.json()["doi_suffix"] == doi


def test_manuscript_token_scoped_to_one_manuscript(client, engine):
    """A manuscript token must not grant access to other manuscripts."""
    doi_a = _create(client, "CCR.TOK.A")
    _create(client, "CCR.TOK.B")
    _create_manuscript_token(engine, doi_a)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.get("/api/manuscripts/CCR.TOK.B")
    assert r.status_code == 404


def test_manuscript_token_list_returns_only_scoped(client, engine):
    """Token-scoped authors listing manuscripts see only their scoped one."""
    doi = _create(client, "CCR.TOK.LIST")
    _create(client, "CCR.TOK.OTHER")
    _create_manuscript_token(engine, doi, "tok-list-test")

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": "Bearer tok-list-test"})

    r = tc.get("/api/manuscripts")
    assert r.status_code == 200
    suffixes = [m["doi_suffix"] for m in r.json()]
    assert suffixes == ["CCR.TOK.LIST"]


def test_manuscript_token_me_endpoint(client, engine):
    """The /me endpoint returns author role and manuscript_token_scope."""
    doi = _create(client)
    _create_manuscript_token(engine, doi)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.get("/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "author"
    assert data["manuscript_token_scope"] == doi
    assert data["username"] is None


def test_manuscript_token_cannot_create(client, engine):
    """Token-scoped authors cannot create manuscripts."""
    doi = _create(client)
    _create_manuscript_token(engine, doi)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.post("/api/manuscripts", json={"doi_suffix": "CCR.NEW"})
    assert r.status_code == 403


@patch("web.backend.app.routes.upload.run_pipeline")
def test_manuscript_token_can_upload(mock_pipeline, client, engine, test_storage):
    """Token-scoped authors can upload to their scoped manuscript."""
    doi = _create(client)
    _create_manuscript_token(engine, doi)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.post(
        f"/api/manuscripts/{doi}/upload",
        files=[("files", ("main.tex", b"x", "text/plain"))],
    )
    assert r.status_code == 201
    assert r.json()["uploaded_by"] == "author"


def test_manuscript_token_presign(client, engine, test_storage):
    """Token-scoped authors can get presign tokens for their manuscript."""
    doi = _create(client)
    _create_manuscript_token(engine, doi)

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {MANUSCRIPT_TOKEN}"})

    r = tc.get(f"/api/manuscripts/{doi}/presign")
    assert r.status_code == 200
    assert "token" in r.json()


def test_invalid_manuscript_token(anon_client):
    """An invalid manuscript token returns 401."""
    anon_client.headers.update({"Authorization": "Bearer bogus-token-123"})
    r = anon_client.get("/api/manuscripts")
    assert r.status_code == 401


# ── Author token generation (editor-only) ────────────────────────────────────


def test_get_author_token(client):
    """Editor can get/create an author token for a manuscript."""
    doi = _create(client)
    r = client.get(f"/api/manuscripts/{doi}/author-token")
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert "url" in data
    assert doi in data["url"]

    # Second call returns the same token
    r2 = client.get(f"/api/manuscripts/{doi}/author-token")
    assert r2.json()["token"] == data["token"]


def test_regenerate_author_token(client):
    """Regenerating an author token invalidates the old one."""
    doi = _create(client)
    r1 = client.get(f"/api/manuscripts/{doi}/author-token")
    old_token = r1.json()["token"]

    r2 = client.post(f"/api/manuscripts/{doi}/author-token/regenerate")
    assert r2.status_code == 200
    new_token = r2.json()["token"]
    assert new_token != old_token

    # Old token should no longer work
    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": f"Bearer {old_token}"})
    r3 = tc.get(f"/api/manuscripts/{doi}")
    assert r3.status_code == 401

    # New token should work
    tc.headers.update({"Authorization": f"Bearer {new_token}"})
    r4 = tc.get(f"/api/manuscripts/{doi}")
    assert r4.status_code == 200


def test_author_token_requires_editor(client, author_client, engine):
    """Non-editors cannot generate author tokens."""
    doi = _create(client)
    r = author_client.get(f"/api/manuscripts/{doi}/author-token")
    assert r.status_code == 403


def test_author_token_not_found(client):
    """Author token for non-existent manuscript returns 404."""
    r = client.get("/api/manuscripts/DOES-NOT-EXIST/author-token")
    assert r.status_code == 404


# ── Approval ─────────────────────────────────────────────────────────────────


def test_approve_manuscript(client, engine):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.APPR"})
    with Session(engine) as session:
        ms = session.get(Manuscript, "CCR2025.1.1.APPR")
        ms.status = "ready"
        session.add(ms)
        session.commit()
    r = client.post("/api/manuscripts/CCR2025.1.1.APPR/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_approve_requires_ready_status(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.APPR2"})
    r = client.post("/api/manuscripts/CCR2025.1.1.APPR2/approve")
    assert r.status_code == 400
    assert "ready" in r.json()["detail"]


def test_token_author_can_approve(client, engine):
    """Token-scoped authors can approve their manuscript."""
    doi = "CCR2025.1.1.APPR3"
    client.post("/api/manuscripts", json={"doi_suffix": doi})
    _create_manuscript_token(engine, doi, "author-approve-tok")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        ms.status = "ready"
        session.add(ms)
        session.commit()

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": "Bearer author-approve-tok"})
    r = tc.post(f"/api/manuscripts/{doi}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_approve_denied_for_wrong_manuscript(client, engine):
    """Token-scoped author cannot approve a different manuscript."""
    _create(client, "CCR.APPR.A")
    _create(client, "CCR.APPR.B")
    _create_manuscript_token(engine, "CCR.APPR.A", "author-appr-wrong")
    with Session(engine) as session:
        ms = session.get(Manuscript, "CCR.APPR.B")
        ms.status = "ready"
        session.add(ms)
        session.commit()

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": "Bearer author-appr-wrong"})
    r = tc.post("/api/manuscripts/CCR.APPR.B/approve")
    assert r.status_code == 404


def test_withdraw_approval(client, engine):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.WD1"})
    with Session(engine) as session:
        ms = session.get(Manuscript, "CCR2025.1.1.WD1")
        ms.status = "approved"
        session.add(ms)
        session.commit()
    r = client.post("/api/manuscripts/CCR2025.1.1.WD1/withdraw-approval")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_withdraw_requires_approved_status(client):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.WD2"})
    r = client.post("/api/manuscripts/CCR2025.1.1.WD2/withdraw-approval")
    assert r.status_code == 400
    assert "approved" in r.json()["detail"]


def test_token_author_can_withdraw(client, engine):
    """Token-scoped authors can withdraw approval on their manuscript."""
    doi = "CCR2025.1.1.WD3"
    client.post("/api/manuscripts", json={"doi_suffix": doi})
    _create_manuscript_token(engine, doi, "author-withdraw-tok")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        ms.status = "approved"
        session.add(ms)
        session.commit()

    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({"Authorization": "Bearer author-withdraw-tok"})
    r = tc.post(f"/api/manuscripts/{doi}/withdraw-approval")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_withdraw_blocked_when_ojs_in_production(client, engine, monkeypatch):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.WD4"})
    with Session(engine) as session:
        ms = session.get(Manuscript, "CCR2025.1.1.WD4")
        ms.status = "approved"
        ms.ojs_submission_id = 99
        session.add(ms)
        session.commit()

    async def fake_in_production(sid, cfg=None):
        return True
    monkeypatch.setattr(ojs_client, "is_submission_in_production", fake_in_production)

    r = client.post("/api/manuscripts/CCR2025.1.1.WD4/withdraw-approval")
    assert r.status_code == 409
    assert "production" in r.json()["detail"]


def test_withdraw_allowed_when_ojs_not_in_production(client, engine, monkeypatch):
    client.post("/api/manuscripts", json={"doi_suffix": "CCR2025.1.1.WD5"})
    with Session(engine) as session:
        ms = session.get(Manuscript, "CCR2025.1.1.WD5")
        ms.status = "approved"
        ms.ojs_submission_id = 99
        session.add(ms)
        session.commit()

    async def fake_not_in_production(sid, cfg=None):
        return False
    monkeypatch.setattr(ojs_client, "is_submission_in_production", fake_not_in_production)

    r = client.post("/api/manuscripts/CCR2025.1.1.WD5/withdraw-approval")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ── Delete ────────────────────────────────────────────────────────────────────


def test_delete_manuscript_wipes_db_and_files(client, engine, test_storage):
    doi = _create(client, "CCR2025.1.1.DEL1")
    test_storage.ensure_dirs(doi)
    sentinel = test_storage.source_dir(doi) / "main.tex"
    sentinel.write_text("\\documentclass{article}")
    with Session(engine) as session:
        session.add(ManuscriptAuthor(manuscript_id=doi, name="A. Author", email="a@example.com"))
        session.add(ManuscriptToken(manuscript_id=doi, token="del1-author-tok"))
        session.commit()

    r = client.delete(f"/api/manuscripts/{doi}")
    assert r.status_code == 204

    with Session(engine) as session:
        assert session.get(Manuscript, doi) is None
        from sqlmodel import select
        assert session.exec(
            select(ManuscriptAuthor).where(ManuscriptAuthor.manuscript_id == doi)
        ).first() is None
        assert session.exec(
            select(ManuscriptToken).where(ManuscriptToken.manuscript_id == doi)
        ).first() is None
    assert not test_storage.manuscript_dir(doi).exists()


def test_delete_manuscript_not_found(client):
    r = client.delete("/api/manuscripts/DOES-NOT-EXIST")
    assert r.status_code == 404


def test_delete_manuscript_blocked_when_approved(client, engine):
    doi = _create(client, "CCR2025.1.1.DEL2")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        ms.status = "approved"
        session.add(ms)
        session.commit()

    r = client.delete(f"/api/manuscripts/{doi}")
    assert r.status_code == 409
    assert "approved" in r.json()["detail"].lower()
    with Session(engine) as session:
        assert session.get(Manuscript, doi) is not None


def test_delete_manuscript_requires_editor(author_client):
    r = author_client.delete(f"/api/manuscripts/{AUTHOR_FIXTURE_DOI}")
    assert r.status_code == 403


# ── Archive ───────────────────────────────────────────────────────────────────


def test_archive_manuscript(client):
    doi = _create(client, "CCR2025.1.1.ARC1")
    r = client.post(f"/api/manuscripts/{doi}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_archive_blocked_when_processing(client, engine):
    doi = _create(client, "CCR2025.1.1.ARC2")
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        ms.status = "processing"
        session.add(ms)
        session.commit()
    r = client.post(f"/api/manuscripts/{doi}/archive")
    assert r.status_code == 409
    assert "processed" in r.json()["detail"].lower()


def test_archive_already_archived(client):
    doi = _create(client, "CCR2025.1.1.ARC3")
    assert client.post(f"/api/manuscripts/{doi}/archive").status_code == 200
    r = client.post(f"/api/manuscripts/{doi}/archive")
    assert r.status_code == 400
    assert "already archived" in r.json()["detail"].lower()


def test_unarchive_manuscript(client):
    doi = _create(client, "CCR2025.1.1.ARC4")
    client.post(f"/api/manuscripts/{doi}/archive")
    r = client.post(f"/api/manuscripts/{doi}/unarchive")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_unarchive_requires_archived(client):
    doi = _create(client, "CCR2025.1.1.ARC5")
    r = client.post(f"/api/manuscripts/{doi}/unarchive")
    assert r.status_code == 400
    assert "archived" in r.json()["detail"].lower()


def test_archive_requires_editor(client, author_client):
    doi = _create(client, "CCR2025.1.1.ARC6")
    assert author_client.post(f"/api/manuscripts/{doi}/archive").status_code == 403
    assert author_client.post(f"/api/manuscripts/{doi}/unarchive").status_code == 403


def test_list_excludes_archived_by_default(client):
    _create(client, "CCR2025.1.1.LST1")
    archived = _create(client, "CCR2025.1.1.LST2")
    client.post(f"/api/manuscripts/{archived}/archive")
    r = client.get("/api/manuscripts")
    assert r.status_code == 200
    doi_suffixes = [m["doi_suffix"] for m in r.json()]
    assert "CCR2025.1.1.LST1" in doi_suffixes
    assert archived not in doi_suffixes


def test_list_includes_archived_when_requested(client):
    _create(client, "CCR2025.1.1.LST3")
    archived = _create(client, "CCR2025.1.1.LST4")
    client.post(f"/api/manuscripts/{archived}/archive")
    r = client.get("/api/manuscripts?include_archived=true")
    assert r.status_code == 200
    doi_suffixes = [m["doi_suffix"] for m in r.json()]
    assert "CCR2025.1.1.LST3" in doi_suffixes
    assert archived in doi_suffixes


# ── OJS import ────────────────────────────────────────────────────────────────


def _set_ojs_subs(submissions):
    ojs_client.set_production_submissions_override(submissions)


def test_list_ojs_submissions_editor(client):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Something",
            authors=(ojs_client.OjsAuthor(name="A Author"),),
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
                ojs_client.OjsAuthor(name="A Author", order=0),
                ojs_client.OjsAuthor(
                    name="Other", order=1, primary_contact=True,
                ),
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
    assert {a.name for a in authors} == {"A Author", "Other"}
    by_name = {a.name: a for a in authors}
    assert by_name["A Author"].primary_contact is False
    assert by_name["Other"].primary_contact is True


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


def test_list_ojs_submissions_accepts_production_stage(client):
    _set_ojs_subs([
        ojs_client.OjsSubmission(
            submission_id=42,
            doi_suffix="CCR2025.1.3.Z",
            title="Backlog",
            authors=(),
        )
    ])
    # The test override ignores the stage filter, but the route should accept
    # stage=production and still return the overridden list.
    r = client.get("/api/ojs/submissions?stage=production")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_ojs_submissions_rejects_unknown_stage(client):
    _set_ojs_subs([])
    r = client.get("/api/ojs/submissions?stage=review")
    assert r.status_code == 422


def test_fetch_production_submissions_uses_stage_id(monkeypatch):
    """Make sure the stage_id argument is forwarded to the OJS query string."""
    import asyncio

    from web.backend.app import ojs as ojs_module

    ojs_module.set_production_submissions_override(None)

    captured_params: list[list[tuple[str, str]]] = []

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"items": [], "itemsMax": 0}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            captured_params.append(list(params))
            return FakeResp()

    monkeypatch.setattr(ojs_module.httpx, "AsyncClient", lambda *a, **k: FakeClient())

    class FakeCfg:
        ojs_admin_token = "tok"
        ojs_base_url = "https://example.test"
        ojs_journal_path = "j"
        ojs_doi_prefix = "10.5117/"

    asyncio.run(
        ojs_module.fetch_production_submissions(cfg=FakeCfg(), stage_id=5)
    )
    assert captured_params
    assert ("stageIds[]", "5") in captured_params[0]


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
    assert len(steps) == 5
    assert [s["name"] for s in steps] == ["prepare", "compile", "convert", "check", "validate"]
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


# ── OJS metadata sync ───────────────────────────────────────────────────────


def _setup_manuscript_with_comparison(engine, test_storage, doi="CCR.SYNC"):
    """Create a manuscript with OJS link and a metadata_comparison.json."""
    with Session(engine) as session:
        session.add(Manuscript(
            doi_suffix=doi,
            ojs_submission_id=42,
            title="OJS Title",
            abstract="OJS abstract",
            keywords=["kw1", "kw2"],
        ))
        session.add(ManuscriptAuthor(
            manuscript_id=doi, name="A Author", order=0,
        ))
        session.commit()

    convert_dir = test_storage.convert_output_dir(doi)
    convert_dir.mkdir(parents=True, exist_ok=True)

    comparison = [
        {"field": "title", "status": "mismatch", "ojs": "OJS Title", "latex": "LaTeX Title"},
        {"field": "abstract", "status": "ok", "ojs": "OJS abstract", "latex": "OJS abstract"},
        {"field": "keywords", "status": "mismatch", "ojs": ["kw1", "kw2"], "latex": ["kw1", "kw3"]},
        {"field": "doi", "status": "mismatch", "ojs": "10.5117/A", "latex": "10.5117/B"},
    ]
    (convert_dir / "metadata_comparison.json").write_text(json.dumps(comparison))

    # Also write a minimal JATS XML for regeneration
    (convert_dir / f"{doi}.xml").write_text(
        '<?xml version="1.0"?>'
        '<article><front><article-meta>'
        '<article-title>LaTeX Title</article-title>'
        '<article-id pub-id-type="doi">10.5117/B</article-id>'
        '</article-meta></front></article>'
    )
    return doi


@patch("web.backend.app.routes.manuscripts.ojs_client.fetch_submission", new_callable=AsyncMock)
@patch("web.backend.app.routes.manuscripts.ojs_client.update_publication_field", new_callable=AsyncMock)
def test_sync_ojs_field_title(mock_update, mock_fetch, client, engine, test_storage):
    doi = _setup_manuscript_with_comparison(engine, test_storage)
    # After push, re-import returns OJS submission with the updated title
    mock_fetch.return_value = ojs_client.OjsSubmission(
        submission_id=42, doi_suffix=doi, title="LaTeX Title",
        authors=(ojs_client.OjsAuthor(name="A Author", order=0),),
    )
    r = client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "title"},
    )
    assert r.status_code == 200
    mock_update.assert_called_once_with(42, "title", "LaTeX Title")

    # Local DB should reflect re-imported OJS data
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        assert ms.title == "LaTeX Title"


@patch("web.backend.app.routes.manuscripts.ojs_client.fetch_submission", new_callable=AsyncMock)
@patch("web.backend.app.routes.manuscripts.ojs_client.update_publication_field", new_callable=AsyncMock)
def test_sync_ojs_field_keywords(mock_update, mock_fetch, client, engine, test_storage):
    doi = _setup_manuscript_with_comparison(engine, test_storage)
    mock_fetch.return_value = ojs_client.OjsSubmission(
        submission_id=42, doi_suffix=doi, title="OJS Title",
        keywords=("kw1", "kw3"),
        authors=(ojs_client.OjsAuthor(name="A Author", order=0),),
    )
    r = client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "keywords"},
    )
    assert r.status_code == 200
    mock_update.assert_called_once_with(42, "keywords", ["kw1", "kw3"])

    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        assert ms.keywords == ["kw1", "kw3"]


def test_sync_ojs_rejects_non_updatable_field(client, engine, test_storage):
    doi = _setup_manuscript_with_comparison(engine, test_storage)
    r = client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "doi"},
    )
    assert r.status_code == 400
    assert "not updatable" in r.json()["detail"]


def test_sync_ojs_rejects_matching_field(client, engine, test_storage):
    doi = _setup_manuscript_with_comparison(engine, test_storage)
    r = client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "abstract"},
    )
    assert r.status_code == 400
    assert "already matches" in r.json()["detail"]


def test_sync_ojs_rejects_author_for_wrong_manuscript(client, author_client, engine, test_storage):
    # author_client is scoped to AUTHOR_FIXTURE_DOI, not CCR.SYNC
    doi = _setup_manuscript_with_comparison(engine, test_storage)
    r = author_client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "title"},
    )
    assert r.status_code == 404


@patch("web.backend.app.routes.manuscripts.ojs_client.fetch_submission", new_callable=AsyncMock)
@patch("web.backend.app.routes.manuscripts.ojs_client.update_publication_field", new_callable=AsyncMock)
def test_sync_ojs_author_can_push(mock_update, mock_fetch, author_client, engine, test_storage):
    doi = AUTHOR_FIXTURE_DOI
    # Upgrade the author's fixture manuscript to be OJS-linked
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        ms.ojs_submission_id = 42
        ms.title = "OJS Title"
        session.add(ms)
        session.add(ManuscriptAuthor(manuscript_id=doi, name="A Author", order=0))
        session.commit()

    convert_dir = test_storage.convert_output_dir(doi)
    convert_dir.mkdir(parents=True, exist_ok=True)
    comparison = [
        {"field": "title", "status": "mismatch", "ojs": "OJS Title", "latex": "LaTeX Title"},
    ]
    (convert_dir / "metadata_comparison.json").write_text(json.dumps(comparison))
    (convert_dir / f"{doi}.xml").write_text(
        '<?xml version="1.0"?>'
        '<article><front><article-meta>'
        '<article-title>LaTeX Title</article-title>'
        '</article-meta></front></article>'
    )

    mock_fetch.return_value = ojs_client.OjsSubmission(
        submission_id=42, doi_suffix=doi, title="LaTeX Title",
        authors=(ojs_client.OjsAuthor(name="A Author", order=0),),
    )
    r = author_client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "title"},
    )
    assert r.status_code == 200
    mock_update.assert_called_once_with(42, "title", "LaTeX Title")


def test_sync_ojs_no_ojs_link(client, engine, test_storage):
    doi = _create(client, "CCR.NOOJS")
    r = client.post(
        f"/api/manuscripts/{doi}/sync-ojs",
        json={"field": "title"},
    )
    assert r.status_code == 400
    assert "not linked" in r.json()["detail"]


def test_sync_ojs_no_comparison_file(client, engine, test_storage):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.NOCOMP", ojs_submission_id=99))
        session.commit()
    r = client.post(
        "/api/manuscripts/CCR.NOCOMP/sync-ojs",
        json={"field": "title"},
    )
    assert r.status_code == 404
    assert "comparison" in r.json()["detail"]


# ── Invite authors ───────────────────────────────────────────────────────────


INVITE_BODY = {
    "subject": "Test invite",
    "body": "Dear Alice, please check.",
    "recipients": [{"name": "Alice", "email": "alice@example.com"}],
}


def test_invite_authors_requires_editor(author_client, engine):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.INV"))
        session.commit()
    r = author_client.post(
        "/api/manuscripts/CCR.INV/invite-authors", json=INVITE_BODY
    )
    assert r.status_code == 403


def test_invite_authors_no_recipients(client, engine):
    cfg_with_smtp = AuthConfig(
        **{**TEST_CFG.__dict__, "smtp_host": "smtp.test", "smtp_from": "test@test.com"}
    )
    set_for_tests(cfg_with_smtp)
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.NOEMAIL", title="Test"))
        session.commit()
    r = client.post(
        "/api/manuscripts/CCR.NOEMAIL/invite-authors",
        json={"subject": "Test", "body": "Dear Author", "recipients": []},
    )
    assert r.status_code == 422
    assert "No recipients" in r.json()["detail"]


def test_invite_authors_smtp_not_configured(client, engine):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.NOSMTP", title="Test"))
        session.commit()
    r = client.post(
        "/api/manuscripts/CCR.NOSMTP/invite-authors", json=INVITE_BODY
    )
    assert r.status_code == 400
    assert "SMTP" in r.json()["detail"]


def test_invite_template(client, engine):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.TPL", title="My Paper"))
        session.add(ManuscriptAuthor(
            manuscript_id="CCR.TPL", name="Alice",
            email="alice@example.com", order=0,
        ))
        session.add(ManuscriptAuthor(
            manuscript_id="CCR.TPL", name="Bob",
            email="bob@example.com", order=1,
        ))
        session.commit()
    r = client.get("/api/manuscripts/CCR.TPL/invite-authors")
    assert r.status_code == 200
    data = r.json()
    assert "My Paper" in data["subject"]
    assert "Dear Alice" in data["body"]
    assert "CCR.TPL" in data["body"]
    # Default recipients: first author only
    assert len(data["recipients"]) == 1
    assert data["recipients"][0]["name"] == "Alice"
    assert data["recipients"][0]["email"] == "alice@example.com"


def test_invite_template_prefers_primary_contact(client, engine):
    """Default recipient should be the primary contact, not the first author."""
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.PRIMARY", title="Paper"))
        session.add(ManuscriptAuthor(
            manuscript_id="CCR.PRIMARY", name="Alice",
            email="alice@example.com", order=0, primary_contact=False,
        ))
        session.add(ManuscriptAuthor(
            manuscript_id="CCR.PRIMARY", name="Bob",
            email="bob@example.com", order=1, primary_contact=True,
        ))
        session.commit()
    r = client.get("/api/manuscripts/CCR.PRIMARY/invite-authors")
    assert r.status_code == 200
    data = r.json()
    assert len(data["recipients"]) == 1
    assert data["recipients"][0]["email"] == "bob@example.com"
    assert "Dear Bob" in data["body"]


def test_invite_authors_success(client, engine):
    cfg_with_smtp = AuthConfig(
        **{**TEST_CFG.__dict__, "smtp_host": "smtp.test", "smtp_from": "test@test.com"}
    )
    set_for_tests(cfg_with_smtp)
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.INVITE", title="My Paper"))
        session.commit()

    with patch(
        "web.backend.app.email._send"
    ) as mock_send:
        r = client.post(
            "/api/manuscripts/CCR.INVITE/invite-authors",
            json={
                "subject": "Check your paper",
                "body": "Dear Alice and Bob, please review.",
                "recipients": [
                    {"name": "Alice", "email": "alice@example.com"},
                    {"name": "Bob", "email": "bob@example.com"},
                ],
            },
        )

    assert r.status_code == 200
    data = r.json()
    assert data["sent"] == ["Alice", "Bob"]
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    # recipients list
    assert call_args[0][0] == [("Alice", "alice@example.com"), ("Bob", "bob@example.com")]
    # subject
    assert call_args[0][1] == "Check your paper"


# ── Orphaned-job reset on startup ──────────────────────────────────────────────


def test_reset_orphaned_jobs_flips_stuck_manuscripts_to_failed(engine):
    """Server restart mid-pipeline: queued/processing rows must become failed."""
    from web.backend.app.main import _reset_orphaned_jobs
    from web.backend.app.worker import init_pipeline_steps

    steps = init_pipeline_steps()
    steps[0]["status"] = "ok"
    steps[1]["status"] = "running"   # compile was mid-flight
    steps[1]["started_at"] = "2026-04-23T19:46:01"

    with Session(engine) as session:
        session.add(Manuscript(
            doi_suffix="STUCK.001", status=ManuscriptStatus.processing,
            pipeline_steps=steps, job_log="some earlier output",
        ))
        session.add(Manuscript(
            doi_suffix="QUEUED.002", status=ManuscriptStatus.queued,
        ))
        session.add(Manuscript(
            doi_suffix="DONE.003", status=ManuscriptStatus.ready,
        ))
        session.commit()

    _reset_orphaned_jobs(engine)

    with Session(engine) as session:
        stuck = session.get(Manuscript, "STUCK.001")
        queued = session.get(Manuscript, "QUEUED.002")
        done = session.get(Manuscript, "DONE.003")

    assert stuck.status == ManuscriptStatus.failed
    assert stuck.job_completed_at is not None
    assert "server restarted" in stuck.job_log
    # The step that was running is now failed; pending steps after it skipped.
    step_statuses = [s["status"] for s in stuck.pipeline_steps]
    assert step_statuses[0] == "ok"
    assert step_statuses[1] == "failed"
    assert all(s == "skipped" for s in step_statuses[2:])

    assert queued.status == ManuscriptStatus.failed
    # Untouched: already-terminal manuscripts stay as they were.
    assert done.status == ManuscriptStatus.ready


def test_reset_orphaned_jobs_noop_when_no_stuck_manuscripts(engine):
    """Clean startup (no stuck rows) must not touch any manuscript."""
    from web.backend.app.main import _reset_orphaned_jobs

    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="A", status=ManuscriptStatus.ready))
        session.add(Manuscript(doi_suffix="B", status=ManuscriptStatus.draft))
        session.commit()

    _reset_orphaned_jobs(engine)

    with Session(engine) as session:
        a = session.get(Manuscript, "A")
        b = session.get(Manuscript, "B")
    assert a.status == ManuscriptStatus.ready
    assert b.status == ManuscriptStatus.draft
    assert a.job_log == ""
    assert b.job_log == ""
