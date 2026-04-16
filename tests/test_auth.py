"""Tests for ORCID OAuth login flow and session dependencies."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web.backend.app import deps, ojs as ojs_module
from web.backend.app.config import AuthConfig, set_for_tests
from web.backend.app.main import app
from web.backend.app.models import AccessToken, LoginState
from web.backend.app.orcid import OrcidAuthError, OrcidIdentity, OrcidUnavailable
from web.backend.app.ojs import OjsUnavailable
from web.backend.app.storage import Storage


TEST_CFG = AuthConfig(
    orcid_client_id="cid",
    orcid_client_secret="sec",
    orcid_env="sandbox",
    orcid_redirect_uri="http://testserver/api/auth/orcid/callback",
    frontend_url="http://frontend",
    ojs_base_url="https://ojs",
    ojs_journal_path="ccr",
    ojs_admin_token="admintok",
    ojs_doi_prefix="10.5117/",
    ojs_editor_cache_ttl_seconds=300,
    session_token_ttl_days=30,
    editor_override_orcids=frozenset(),
)


@pytest.fixture(autouse=True)
def _cfg():
    set_for_tests(TEST_CFG)
    ojs_module._cache_clear()
    yield
    ojs_module._cache_clear()


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


def _seed_state(engine, state: str = "abc"):
    with Session(engine) as session:
        session.add(LoginState(state=state))
        session.commit()


# ── /orcid/login ──────────────────────────────────────────────────────────────


def test_login_redirects_to_orcid(client, engine):
    r = client.get("/api/auth/orcid/login")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://sandbox.orcid.org/oauth/authorize?")
    assert "state=" in loc
    assert "client_id=cid" in loc
    with Session(engine) as session:
        assert session.exec(select(LoginState)).first() is not None


# ── /orcid/callback ──────────────────────────────────────────────────────────


def test_callback_editor_success(client, engine):
    _seed_state(engine, "s1")
    with patch(
        "web.backend.app.routes.auth.orcid_client.exchange_code",
        new=AsyncMock(return_value=OrcidIdentity(orcid="0000-0000-0000-0002", name="Ed")),
    ), patch(
        "web.backend.app.routes.auth.ojs_client.fetch_editor_orcids",
        new=AsyncMock(return_value=frozenset({"0000-0000-0000-0002"})),
    ):
        r = client.get("/api/auth/orcid/callback?code=xyz&state=s1")
    assert r.status_code == 302
    assert r.headers["location"].startswith("http://frontend/auth/complete#token=")
    with Session(engine) as session:
        row = session.exec(select(AccessToken)).first()
        assert row is not None
        assert row.orcid == "0000-0000-0000-0002"


def test_callback_non_editor_allowed(client, engine):
    """Non-editor ORCID users also get a session token; role is derived later."""
    _seed_state(engine, "s3")
    with patch(
        "web.backend.app.routes.auth.orcid_client.exchange_code",
        new=AsyncMock(return_value=OrcidIdentity(orcid="0000-0000-0000-0004", name="Author")),
    ), patch(
        "web.backend.app.routes.auth.ojs_client.fetch_editor_orcids",
        new=AsyncMock(return_value=frozenset()),
    ):
        r = client.get("/api/auth/orcid/callback?code=xyz&state=s3")
    assert r.status_code == 302
    assert r.headers["location"].startswith("http://frontend/auth/complete#token=")
    with Session(engine) as session:
        row = session.exec(select(AccessToken)).first()
        assert row is not None
        assert row.orcid == "0000-0000-0000-0004"


def test_callback_invalid_state(client, engine):
    r = client.get("/api/auth/orcid/callback?code=xyz&state=nope")
    assert r.status_code == 400


def test_callback_orcid_auth_error(client, engine):
    _seed_state(engine, "s4")
    with patch(
        "web.backend.app.routes.auth.orcid_client.exchange_code",
        new=AsyncMock(side_effect=OrcidAuthError("bad code")),
    ):
        r = client.get("/api/auth/orcid/callback?code=xyz&state=s4")
    assert r.status_code == 401


def test_callback_orcid_unavailable(client, engine):
    _seed_state(engine, "s5")
    with patch(
        "web.backend.app.routes.auth.orcid_client.exchange_code",
        new=AsyncMock(side_effect=OrcidUnavailable("timeout")),
    ):
        r = client.get("/api/auth/orcid/callback?code=xyz&state=s5")
    assert r.status_code == 502


def test_callback_ojs_unavailable_still_allows_login(client, engine):
    """OJS unreachable during login should not block the session — the role
    lookup is deferred to later requests."""
    _seed_state(engine, "s6")
    with patch(
        "web.backend.app.routes.auth.orcid_client.exchange_code",
        new=AsyncMock(return_value=OrcidIdentity(orcid="0000-0000-0000-0005", name="U")),
    ), patch(
        "web.backend.app.routes.auth.ojs_client.fetch_editor_orcids",
        new=AsyncMock(side_effect=OjsUnavailable("down")),
    ):
        r = client.get("/api/auth/orcid/callback?code=xyz&state=s6")
    assert r.status_code == 302
    assert r.headers["location"].startswith("http://frontend/auth/complete#token=")
    with Session(engine) as session:
        assert session.exec(select(AccessToken)).first() is not None


# ── /me and /logout ──────────────────────────────────────────────────────────


def test_me_returns_current_user_with_role(client, engine):
    with Session(engine) as session:
        session.add(
            AccessToken(token="tok1", orcid="0000-0000-0000-0006", name="Ed")
        )
        session.commit()
    with patch(
        "web.backend.app.deps.ojs_client.fetch_editor_orcids",
        new=AsyncMock(return_value=frozenset({"0000-0000-0000-0006"})),
    ):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer tok1"})
    assert r.status_code == 200
    assert r.json() == {
        "orcid": "0000-0000-0000-0006",
        "name": "Ed",
        "role": "editor",
        "manuscript_token_scope": None,
    }


def test_me_without_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_deletes_token(client, engine):
    with Session(engine) as session:
        session.add(AccessToken(token="tok2", orcid="0000-0000-0000-0007"))
        session.commit()
    r = client.post("/api/auth/logout", headers={"Authorization": "Bearer tok2"})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer tok2"}).status_code == 401
