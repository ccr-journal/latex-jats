"""OJS REST client.

Only used for the editor-ORCID lookup that gates editor login. The backend
holds a journal-admin OJS API token in `OJS_ADMIN_TOKEN` and queries the list
of users with Journal Manager (role 16) or Section Editor (role 17) roles.
The returned `orcid` values form the authoritative set of CCR editors.
"""

from __future__ import annotations

import logging
import time

import httpx

from .config import AuthConfig, get_config, normalize_orcid

logger = logging.getLogger("latex_jats.web.ojs")

_ROLE_MANAGER = 16
_ROLE_SECTION_EDITOR = 17
_PAGE_SIZE = 100


class OjsUnavailable(Exception):
    pass


class OjsAdminTokenInvalid(Exception):
    pass


_cache: tuple[float, frozenset[str]] | None = None


def _cache_clear() -> None:
    global _cache
    _cache = None


async def fetch_editor_orcids(cfg: AuthConfig | None = None) -> frozenset[str]:
    global _cache
    cfg = cfg or get_config()
    now = time.monotonic()
    if _cache is not None:
        ts, value = _cache
        if now - ts < cfg.ojs_editor_cache_ttl_seconds:
            return value

    # Dev mode: no real OJS credentials; use only the override set.
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        result = frozenset(cfg.editor_override_orcids)
        _cache = (now, result)
        logger.info(
            "OJS admin token not configured; using %d override ORCIDs",
            len(result),
        )
        return result

    url = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1/users"
    )
    headers = {"Authorization": f"Bearer {cfg.ojs_admin_token}"}
    params: list[tuple[str, str]] = [
        ("roleIds[]", str(_ROLE_MANAGER)),
        ("roleIds[]", str(_ROLE_SECTION_EDITOR)),
        ("count", str(_PAGE_SIZE)),
        ("offset", "0"),
    ]

    found: set[str] = set()
    offset = 0
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                page_params = [
                    ("roleIds[]", str(_ROLE_MANAGER)),
                    ("roleIds[]", str(_ROLE_SECTION_EDITOR)),
                    ("count", str(_PAGE_SIZE)),
                    ("offset", str(offset)),
                ]
                resp = await client.get(url, headers=headers, params=page_params)
                if resp.status_code in (401, 403):
                    raise OjsAdminTokenInvalid(
                        f"OJS rejected admin token ({resp.status_code}): {resp.text[:200]}"
                    )
                if resp.status_code >= 500 or resp.status_code >= 400:
                    raise OjsUnavailable(
                        f"OJS returned {resp.status_code}: {resp.text[:200]}"
                    )
                payload = resp.json()
                items = payload.get("items") or []
                for item in items:
                    normalized = normalize_orcid(item.get("orcid"))
                    if normalized:
                        found.add(normalized)
                items_max = payload.get("itemsMax") or 0
                offset += len(items)
                if not items or offset >= items_max:
                    break
    except httpx.RequestError as exc:
        raise OjsUnavailable(str(exc)) from exc

    if cfg.editor_override_orcids:
        found.update(cfg.editor_override_orcids)
        logger.info(
            "Merged %d override ORCIDs into editor set (dev only)",
            len(cfg.editor_override_orcids),
        )

    result = frozenset(found)
    _cache = (now, result)
    logger.info("Refreshed CCR editor ORCID set from OJS (%d entries)", len(result))
    return result
