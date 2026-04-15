"""Auth-related configuration read from environment variables.

Values are read at module load and cached; call reload() from tests that need
to override them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthConfig:
    orcid_client_id: str
    orcid_client_secret: str
    orcid_env: str  # "sandbox" | "production"
    orcid_redirect_uri: str
    frontend_url: str
    ojs_base_url: str
    ojs_journal_path: str
    ojs_admin_token: str
    ojs_editor_cache_ttl_seconds: int
    session_token_ttl_days: int
    # Dev-only: merged into the fetched editor set. Comma-separated ORCIDs.
    editor_override_orcids: frozenset[str]

    @property
    def orcid_base_url(self) -> str:
        return (
            "https://sandbox.orcid.org"
            if self.orcid_env == "sandbox"
            else "https://orcid.org"
        )


def _load() -> AuthConfig:
    def req(key: str) -> str:
        v = os.environ.get(key, "")
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    def opt(key: str, default: str) -> str:
        return os.environ.get(key, default)

    overrides = {
        o.strip() for o in opt("OJS_EDITOR_OVERRIDE_ORCIDS", "").split(",") if o.strip()
    }

    # When OJS_EDITOR_OVERRIDE_ORCIDS is set (dev mode), the OJS lookup is
    # optional — we can run without a real OJS admin token.
    has_overrides = bool(overrides)

    def ojs_req(key: str, default: str = "") -> str:
        if has_overrides:
            return opt(key, default)
        return req(key)

    # In production we deploy behind SITE_ADDRESS (set in .env alongside the
    # docker-compose config); derive ORCID_REDIRECT_URI and FRONTEND_URL from
    # it so prod only needs the one value.
    site_address = opt("SITE_ADDRESS", "")
    # Only upgrade to https:// for real domains; localhost stays on http://
    # (Caddy serves localhost over HTTP, no TLS cert).
    if site_address and site_address not in ("localhost", "127.0.0.1"):
        site_origin = f"https://{site_address}"
    elif site_address:
        site_origin = f"http://{site_address}"
    else:
        site_origin = ""

    return AuthConfig(
        orcid_client_id=req("ORCID_CLIENT_ID"),
        orcid_client_secret=req("ORCID_CLIENT_SECRET"),
        orcid_env=opt("ORCID_ENV", "production"),
        orcid_redirect_uri=opt(
            "ORCID_REDIRECT_URI",
            f"{site_origin}/api/auth/orcid/callback"
            if site_origin
            else "http://127.0.0.1:8000/api/auth/orcid/callback",
        ),
        frontend_url=opt(
            "FRONTEND_URL",
            site_origin if site_origin else "http://127.0.0.1:5173",
        ),
        ojs_base_url=ojs_req("OJS_BASE_URL"),
        ojs_journal_path=ojs_req("OJS_JOURNAL_PATH", "ccr"),
        ojs_admin_token=ojs_req("OJS_ADMIN_TOKEN"),
        ojs_editor_cache_ttl_seconds=int(opt("OJS_EDITOR_CACHE_TTL_SECONDS", "300")),
        session_token_ttl_days=int(opt("SESSION_TOKEN_TTL_DAYS", "30")),
        editor_override_orcids=frozenset(overrides),
    )


_cfg: AuthConfig | None = None


def get_config() -> AuthConfig:
    global _cfg
    if _cfg is None:
        _cfg = _load()
    return _cfg


def reload() -> AuthConfig:
    global _cfg
    _cfg = _load()
    return _cfg


def set_for_tests(cfg: AuthConfig) -> None:
    global _cfg
    _cfg = cfg


def normalize_orcid(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/", "https://sandbox.orcid.org/"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
            break
    return v or None
