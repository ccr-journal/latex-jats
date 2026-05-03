"""Tests for web/backend/app/config.py — the env → AuthConfig loader.

Focused on the SITE_ADDRESS → frontend_url derivation, which is the bit that
went wrong in v1.0.0 / v1.0.1 when SITE_ADDRESS gained an explicit-scheme
shape (``http://localhost``) for the local-trial Caddy config.
"""

from __future__ import annotations

import pytest

from web.backend.app import config as cfg_module


_BASE_ENV = {
    "EDITOR_CREDENTIALS": "editor:devpass",
    # Required only when OJS_ADMIN_TOKEN is set; left out so the rest of the
    # config keeps loading without OJS plumbing.
}


@pytest.fixture
def env(monkeypatch):
    """Wipe the SITE_ADDRESS / FRONTEND_URL / OJS env so each test starts clean."""
    for k in (
        "SITE_ADDRESS", "FRONTEND_URL",
        "OJS_ADMIN_TOKEN", "OJS_BASE_URL", "OJS_JOURNAL_PATH",
        "SESSION_TOKEN_TTL_DAYS",
    ):
        monkeypatch.delenv(k, raising=False)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def test_site_address_with_http_scheme_used_verbatim(env):
    """Local-trial default. SITE_ADDRESS=http://localhost → frontend_url=
    http://localhost (no scheme manipulation, no auto-https upgrade)."""
    env.setenv("SITE_ADDRESS", "http://localhost")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "http://localhost"


def test_site_address_with_https_scheme_used_verbatim(env):
    """Operator can pin https:// explicitly (e.g. behind a TLS-terminating
    proxy with its own cert) and we honour it."""
    env.setenv("SITE_ADDRESS", "https://jats.example.com")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "https://jats.example.com"


def test_bare_hostname_gets_https(env):
    """Production default for public deploys: bare hostname → https://."""
    env.setenv("SITE_ADDRESS", "jats.example.com")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "https://jats.example.com"


def test_bare_localhost_falls_back_to_http(env):
    """Backwards-compat: a bare ``localhost`` (no scheme) still resolves to
    http://localhost rather than https — Caddy in that legacy config served
    HTTPS via local CA, but the api side never benefited from upgrading."""
    env.setenv("SITE_ADDRESS", "localhost")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "http://localhost"


def test_bare_loopback_ip_falls_back_to_http(env):
    env.setenv("SITE_ADDRESS", "127.0.0.1")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "http://127.0.0.1"


def test_explicit_frontend_url_overrides_site_address(env):
    """When SITE_ADDRESS and FRONTEND_URL disagree (TLS-terminating proxy
    in front of jatsmith), FRONTEND_URL wins."""
    env.setenv("SITE_ADDRESS", "internal.example.com")
    env.setenv("FRONTEND_URL", "https://public.example.com")
    cfg = cfg_module._load()
    assert cfg.frontend_url == "https://public.example.com"


def test_no_site_address_uses_dev_fallback(env):
    """No SITE_ADDRESS, no FRONTEND_URL — fall back to the Vite dev port so
    `uv run uvicorn ...` outside Docker still produces working author-invite
    links."""
    cfg = cfg_module._load()
    assert cfg.frontend_url == "http://127.0.0.1:5173"
