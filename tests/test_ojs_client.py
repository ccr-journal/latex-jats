"""Tests for the OJS editor-lookup client."""

import asyncio

import pytest
import respx
from httpx import Response

from web.backend.app import ojs
from web.backend.app.config import AuthConfig, set_for_tests


@pytest.fixture
def cfg():
    c = AuthConfig(
        orcid_client_id="x",
        orcid_client_secret="x",
        orcid_env="sandbox",
        orcid_redirect_uri="x",
        frontend_url="x",
        ojs_base_url="https://ojs.example.org",
        ojs_journal_path="ccr",
        ojs_admin_token="admin",
        ojs_doi_prefix="10.5117/",
        ojs_editor_cache_ttl_seconds=300,
        session_token_ttl_days=30,
        editor_override_orcids=frozenset({"0000-0000-0000-9999"}),
    )
    set_for_tests(c)
    ojs._cache_clear()
    yield c
    ojs._cache_clear()


def _run(coro):
    return asyncio.run(coro)


@respx.mock
def test_editor_fetch(cfg):
    respx.get("https://ojs.example.org/index.php/ccr/api/v1/users").mock(
        return_value=Response(
            200,
            json={
                "itemsMax": 2,
                "items": [
                    {"id": 1, "orcid": "https://orcid.org/0000-0000-0000-0001"},
                    {"id": 2, "orcid": "0000-0000-0000-0002"},
                ],
            },
        )
    )
    orcids = _run(ojs.fetch_editor_orcids())
    assert "0000-0000-0000-0001" in orcids
    assert "0000-0000-0000-0002" in orcids
    assert "0000-0000-0000-9999" in orcids  # dev override merged


@respx.mock
def test_editor_fetch_caches(cfg):
    route = respx.get("https://ojs.example.org/index.php/ccr/api/v1/users").mock(
        return_value=Response(
            200, json={"itemsMax": 1, "items": [{"orcid": "0000-0000-0000-0001"}]}
        )
    )
    _run(ojs.fetch_editor_orcids())
    _run(ojs.fetch_editor_orcids())
    assert route.call_count == 1  # second call hits cache


@respx.mock
def test_editor_fetch_unauthorized(cfg):
    respx.get("https://ojs.example.org/index.php/ccr/api/v1/users").mock(
        return_value=Response(401, text="unauthorized")
    )
    with pytest.raises(ojs.OjsAdminTokenInvalid):
        _run(ojs.fetch_editor_orcids())


@respx.mock
def test_editor_fetch_pagination(cfg):
    route = respx.get("https://ojs.example.org/index.php/ccr/api/v1/users").mock(
        side_effect=[
            Response(
                200,
                json={
                    "itemsMax": 3,
                    "items": [
                        {"orcid": "0000-0000-0000-0001"},
                        {"orcid": "0000-0000-0000-0002"},
                    ],
                },
            ),
            Response(
                200,
                json={"itemsMax": 3, "items": [{"orcid": "0000-0000-0000-0003"}]},
            ),
        ]
    )
    orcids = _run(ojs.fetch_editor_orcids())
    assert route.call_count == 2
    assert "0000-0000-0000-0003" in orcids
