"""ORCID OAuth client (public API, /authenticate scope).

Uses the authorization-code flow: build_authorize_url() produces the URL the
browser is redirected to; exchange_code() trades an authorization code for the
ORCID iD + display name.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import AuthConfig, get_config, normalize_orcid


class OrcidAuthError(Exception):
    """ORCID rejected the authorization code (invalid, expired, or replayed)."""


class OrcidUnavailable(Exception):
    """ORCID token endpoint returned 5xx or was unreachable."""


@dataclass(frozen=True)
class OrcidIdentity:
    orcid: str
    name: str | None


def build_authorize_url(state: str, cfg: AuthConfig | None = None) -> str:
    cfg = cfg or get_config()
    params = {
        "client_id": cfg.orcid_client_id,
        "response_type": "code",
        "scope": "/authenticate",
        "redirect_uri": cfg.orcid_redirect_uri,
        "state": state,
    }
    return f"{cfg.orcid_base_url}/oauth/authorize?{urlencode(params)}"


async def exchange_code(code: str, cfg: AuthConfig | None = None) -> OrcidIdentity:
    cfg = cfg or get_config()
    url = f"{cfg.orcid_base_url}/oauth/token"
    data = {
        "client_id": cfg.orcid_client_id,
        "client_secret": cfg.orcid_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.orcid_redirect_uri,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data=data,
                headers={"Accept": "application/json"},
            )
    except httpx.RequestError as exc:
        raise OrcidUnavailable(str(exc)) from exc

    if resp.status_code >= 500:
        raise OrcidUnavailable(f"ORCID token endpoint returned {resp.status_code}")
    if resp.status_code >= 400:
        raise OrcidAuthError(f"ORCID rejected code: {resp.status_code} {resp.text[:200]}")

    payload = resp.json()
    orcid = normalize_orcid(payload.get("orcid"))
    if not orcid:
        raise OrcidAuthError("ORCID response missing `orcid` field")
    return OrcidIdentity(orcid=orcid, name=payload.get("name"))
