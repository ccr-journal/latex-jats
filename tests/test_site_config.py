"""Tests for /api/site-config (Issue #32 — externalize journal metadata)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web.backend.app import deps
from web.backend.app.main import app
from web.backend.app.models import (
    AccessToken,
    Manuscript,
    ManuscriptToken,
    SiteConfig,
)
from web.backend.app.storage import Storage


_EDITOR_TOKEN = "site-config-editor-token"
_AUTHOR_DOI = "TEST.AUTHOR.DOI"
_AUTHOR_TOKEN = "site-config-author-token"


def _seed_site_config(engine):
    with Session(engine) as session:
        if session.get(SiteConfig, 1) is not None:
            return
        session.add(SiteConfig(
            id=1,
            journal_id="MYJOURNAL",
            journal_title="My Journal Name",
            issn_epub="1234-5678",
            issn_ppub="",
            publisher_name="My Publisher",
            publisher_loc="City",
            copyright_holder="The authors",
            copyright_statement="© The authors",
            license_type="open-access",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            license_text=(
                "This is an open access article distributed under the CC BY 4.0 license"
            ),
            doi_prefix="10.0000/",
        ))
        session.commit()


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(e)
    _seed_site_config(e)
    return e


@pytest.fixture
def anon_client(engine, tmp_path: Path):
    def override_session():
        with Session(engine) as session:
            yield session

    storage = Storage(tmp_path)

    app.dependency_overrides[deps.get_session] = override_session
    app.dependency_overrides[deps.get_storage] = lambda: storage
    deps._engine = engine
    yield TestClient(app)
    app.dependency_overrides.clear()
    deps._engine = None


@pytest.fixture
def client(anon_client, engine):
    with Session(engine) as session:
        session.add(AccessToken(
            id=str(uuid.uuid4()),
            token=_EDITOR_TOKEN,
            username="editor",
            name="Test Editor",
            created_at=datetime.utcnow(),
        ))
        session.commit()
    anon_client.headers.update({"Authorization": f"Bearer {_EDITOR_TOKEN}"})
    return anon_client


@pytest.fixture
def author_client(anon_client, engine):
    with Session(engine) as session:
        session.add(Manuscript(doi_suffix=_AUTHOR_DOI))
        session.add(ManuscriptToken(
            manuscript_id=_AUTHOR_DOI,
            token=_AUTHOR_TOKEN,
            created_at=datetime.utcnow(),
        ))
        session.commit()
    # New client so we don't share Authorization with the editor fixture
    fresh = TestClient(app)
    fresh.headers.update({"Authorization": f"Bearer {_AUTHOR_TOKEN}"})
    return fresh


def test_get_returns_seeded_placeholders(client):
    r = client.get("/api/site-config")
    assert r.status_code == 200
    body = r.json()
    assert body["journal_id"] == "MYJOURNAL"
    assert body["journal_title"] == "My Journal Name"
    assert body["publisher_name"] == "My Publisher"
    assert body["doi_prefix"] == "10.0000/"
    assert body["configured_at"] is None  # first-run banner shows


def test_get_is_unauthenticated(anon_client):
    """Frontend needs the journal title before login (header text)."""
    r = anon_client.get("/api/site-config")
    assert r.status_code == 200


def test_put_requires_editor(author_client):
    r = author_client.put(
        "/api/site-config",
        json={"journal_title": "Hostile Takeover"},
    )
    assert r.status_code == 403


def test_put_updates_fields_and_sets_configured_at(client, engine):
    r = client.put(
        "/api/site-config",
        json={
            "journal_title": "Journal of New Things",
            "issn_epub": "9999-0000",
            "publisher_name": "New Publisher",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["journal_title"] == "Journal of New Things"
    assert body["issn_epub"] == "9999-0000"
    assert body["publisher_name"] == "New Publisher"
    # Untouched fields stay at the seeded placeholders
    assert body["journal_id"] == "MYJOURNAL"
    # First save sets configured_at
    assert body["configured_at"] is not None

    with Session(engine) as session:
        row = session.get(SiteConfig, 1)
        assert row.journal_title == "Journal of New Things"
        assert row.configured_at is not None


def test_put_keeps_configured_at_stable_after_first_save(client, engine):
    r1 = client.put("/api/site-config", json={"journal_title": "First"})
    assert r1.status_code == 200
    first_configured_at = r1.json()["configured_at"]
    assert first_configured_at is not None

    r2 = client.put("/api/site-config", json={"journal_title": "Second"})
    assert r2.status_code == 200
    assert r2.json()["configured_at"] == first_configured_at
    assert r2.json()["journal_title"] == "Second"


def test_default_matches_migration_seed():
    """Regression guard: DEFAULT_SITE_CONFIG must mirror the 0012 seed.

    The seed lives in a file whose name starts with a digit, so we load it
    by path rather than via a normal import.
    """
    import importlib.util

    from jatsmith.site_config import DEFAULT_SITE_CONFIG

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "web/backend/alembic/versions/0012_add_site_config.py"
    )
    spec = importlib.util.spec_from_file_location("mig0012", mig_path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    seed = mig._DEFAULT_SEED
    for field in (
        "journal_id", "journal_title", "issn_epub", "issn_ppub",
        "publisher_name", "publisher_loc",
        "copyright_holder", "copyright_statement",
        "license_type", "license_url", "license_text",
        "doi_prefix",
    ):
        assert seed[field] == getattr(DEFAULT_SITE_CONFIG, field), (
            f"Mismatch on {field}: migration seed={seed[field]!r} vs "
            f"DEFAULT_SITE_CONFIG={getattr(DEFAULT_SITE_CONFIG, field)!r}"
        )
