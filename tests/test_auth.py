"""Tests for password login flow and session dependencies."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web.backend.app import deps
from web.backend.app.config import AuthConfig, set_for_tests
from web.backend.app.main import app
from web.backend.app.models import AccessToken, ManuscriptToken, Manuscript
from web.backend.app.storage import Storage


TEST_CFG = AuthConfig(
    editor_credentials={"editor": "testpass", "alice": "alice-pw"},
    frontend_url="http://frontend",
    ojs_base_url="https://ojs",
    ojs_journal_path="ccr",
    ojs_admin_token="admintok",
    ojs_doi_prefix="10.5117/",
    session_token_ttl_days=30,
)


@pytest.fixture(autouse=True)
def _cfg():
    set_for_tests(TEST_CFG)
    yield


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
def client(tmp_path: Path, engine):
    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[deps.get_session] = override_session
    app.dependency_overrides[deps.get_storage] = lambda: Storage(tmp_path)
    deps._engine = engine
    yield TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    app.dependency_overrides.clear()
    deps._engine = None


# ── /login ────────────────────────────────────────────────────────────────────


def test_login_success(client, engine):
    r = client.post(
        "/api/auth/login",
        json={"username": "editor", "password": "testpass"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {
        "username": "editor",
        "name": None,
        "role": "editor",
        "manuscript_token_scope": None,
    }
    assert body["token"]
    with Session(engine) as session:
        row = session.exec(select(AccessToken)).first()
        assert row is not None
        assert row.username == "editor"
        assert row.token == body["token"]


def test_login_second_user(client, engine):
    r = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "alice-pw"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "alice"


def test_login_bad_password(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "editor", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid username or password"}


def test_login_unknown_user(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid username or password"}


# ── /me ──────────────────────────────────────────────────────────────────────


def test_me_returns_editor_for_logged_in_user(client, engine):
    with Session(engine) as session:
        session.add(AccessToken(token="tok1", username="editor", name=None))
        session.commit()
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer tok1"})
    assert r.status_code == 200
    assert r.json() == {
        "username": "editor",
        "name": None,
        "role": "editor",
        "manuscript_token_scope": None,
    }


def test_me_returns_author_for_manuscript_token(client, engine):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix="CCR.TEST"))
        session.add(ManuscriptToken(manuscript_id="CCR.TEST", token="authtok"))
        session.commit()
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer authtok"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "author"
    assert body["manuscript_token_scope"] == "CCR.TEST"


def test_me_without_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_invalid_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# ── /logout ──────────────────────────────────────────────────────────────────


def test_logout_deletes_token(client, engine):
    with Session(engine) as session:
        session.add(AccessToken(token="tok2", username="editor"))
        session.commit()
    r = client.post("/api/auth/logout", headers={"Authorization": "Bearer tok2"})
    assert r.status_code == 204
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer tok2"}).status_code
        == 401
    )
