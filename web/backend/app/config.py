"""Auth-related configuration read from environment variables.

Values are read at module load and cached; call reload() from tests that need
to override them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AuthConfig:
    editor_credentials: Mapping[str, str]  # {username: password}
    frontend_url: str
    ojs_base_url: str
    ojs_journal_path: str
    ojs_admin_token: str
    ojs_doi_prefix: str
    session_token_ttl_days: int
    # Fernet key (base64-urlsafe, 32 bytes) for encrypting upstream git tokens
    # at rest. Empty in dev triggers an ephemeral key + loud warning.
    storage_secret_key: str = ""
    # SMTP (optional — enables "Invite authors" email)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


def _parse_editor_credentials(raw: str) -> dict[str, str]:
    """Parse EDITOR_CREDENTIALS env value.

    Formats:
    - plain string (no ``,`` or ``:``): single user ``editor`` with that password.
    - pairs: ``user1:pw1,user2:pw2`` (comma-separated ``user:pass`` entries).
    """
    raw = raw.strip()
    if not raw:
        raise RuntimeError("EDITOR_CREDENTIALS is empty")
    if "," not in raw and ":" not in raw:
        return {"editor": raw}
    creds: dict[str, str] = {}
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if ":" not in piece:
            raise RuntimeError(
                f"EDITOR_CREDENTIALS entry '{piece}' has no ':' separator"
            )
        user, _, password = piece.partition(":")
        user = user.strip()
        if not user or not password:
            raise RuntimeError(
                f"EDITOR_CREDENTIALS entry '{piece}' has empty username or password"
            )
        if user in creds:
            raise RuntimeError(f"EDITOR_CREDENTIALS has duplicate username '{user}'")
        creds[user] = password
    if not creds:
        raise RuntimeError("EDITOR_CREDENTIALS parsed to no entries")
    return creds


def _load() -> AuthConfig:
    def req(key: str) -> str:
        v = os.environ.get(key, "")
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    def opt(key: str, default: str) -> str:
        return os.environ.get(key, default)

    # In production we deploy behind SITE_ADDRESS (set in .env alongside the
    # docker-compose config); derive FRONTEND_URL from it so prod only needs
    # the one value.
    site_address = opt("SITE_ADDRESS", "")
    # Only upgrade to https:// for real domains; localhost stays on http://
    # (Caddy serves localhost over HTTP, no TLS cert).
    if site_address and site_address not in ("localhost", "127.0.0.1"):
        site_origin = f"https://{site_address}"
    elif site_address:
        site_origin = f"http://{site_address}"
    else:
        site_origin = ""

    # OJS fields are required only when OJS_ADMIN_TOKEN is set. Dev runs
    # without OJS by leaving the token unset; OJS-gated endpoints then error
    # at call time rather than blocking startup.
    ojs_admin_token = opt("OJS_ADMIN_TOKEN", "")
    ojs_base_url = req("OJS_BASE_URL") if ojs_admin_token else opt("OJS_BASE_URL", "")

    return AuthConfig(
        editor_credentials=_parse_editor_credentials(req("EDITOR_CREDENTIALS")),
        frontend_url=opt(
            "FRONTEND_URL",
            site_origin if site_origin else "http://127.0.0.1:5173",
        ),
        ojs_base_url=ojs_base_url,
        ojs_journal_path=opt("OJS_JOURNAL_PATH", "ccr"),
        ojs_admin_token=ojs_admin_token,
        ojs_doi_prefix=opt("OJS_DOI_PREFIX", "10.5117/"),
        session_token_ttl_days=int(opt("SESSION_TOKEN_TTL_DAYS", "30")),
        storage_secret_key=opt("STORAGE_SECRET_KEY", ""),
        smtp_host=opt("SMTP_HOST", ""),
        smtp_port=int(opt("SMTP_PORT", "587")),
        smtp_user=opt("SMTP_USER", ""),
        smtp_password=opt("SMTP_PASSWORD", ""),
        smtp_from=opt("SMTP_FROM", ""),
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
