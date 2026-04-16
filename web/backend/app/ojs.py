"""OJS REST client.

Used for two things:

1. Editor-ORCID lookup (see fetch_editor_orcids) — the authoritative set of
   CCR editors, used to determine whether a logged-in ORCID user has editor
   privileges.
2. Production-submission listing (see fetch_production_submissions) — used by
   the "create manuscript" picker in the frontend. Returns submissions
   currently in OJS production stage (stageId 5), with their DOI suffix and
   author ORCIDs.

The backend holds a journal-admin OJS API token in `OJS_ADMIN_TOKEN`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace

import httpx

from .config import AuthConfig, get_config, normalize_orcid

logger = logging.getLogger("latex_jats.web.ojs")

_ROLE_MANAGER = 16
_ROLE_SECTION_EDITOR = 17
_STAGE_PRODUCTION = 5
_PAGE_SIZE = 100


@dataclass(frozen=True)
class OjsAuthor:
    orcid: str
    name: str | None = None
    order: int = 0


@dataclass(frozen=True)
class OjsSubmission:
    submission_id: int
    doi_suffix: str
    title: str
    authors: tuple[OjsAuthor, ...] = field(default_factory=tuple)
    doi: str | None = None
    abstract: str | None = None  # HTML
    keywords: tuple[str, ...] = field(default_factory=tuple)
    volume: str | None = None
    issue_number: str | None = None
    year: int | None = None


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


# ── Production submissions ────────────────────────────────────────────────────

# Test hook: when non-None, fetch_production_submissions returns this directly
# without making an HTTP request. Set in tests that need canned data.
_production_submissions_override: list[OjsSubmission] | None = None

# Short in-process cache for the (slow) production submissions list so the
# picker reopens instantly. Editors importing a submission see it disappear
# from the list on next open; a 60s TTL keeps the window small.
_production_cache: tuple[float, list[OjsSubmission]] | None = None
_PRODUCTION_CACHE_TTL = 60.0


def set_production_submissions_override(subs: list[OjsSubmission] | None) -> None:
    global _production_submissions_override, _production_cache
    _production_submissions_override = subs
    _production_cache = None


def invalidate_production_cache() -> None:
    global _production_cache
    _production_cache = None


def _extract_doi_suffix(doi: str | None, prefix: str) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    if prefix and doi.startswith(prefix):
        return doi[len(prefix):] or None
    # Fall back: take everything after the last slash (DOI prefix is registrant/code).
    if "/" in doi:
        return doi.split("/", 1)[1] or None
    return doi or None


def _parse_authors(publication: dict) -> tuple[OjsAuthor, ...]:
    authors_raw = publication.get("authors") or []
    out: list[OjsAuthor] = []
    for idx, a in enumerate(authors_raw):
        orcid = normalize_orcid(a.get("orcid"))
        if not orcid:
            continue
        given = (a.get("givenName") or {}).get("en") or a.get("givenName") or ""
        family = (a.get("familyName") or {}).get("en") or a.get("familyName") or ""
        if isinstance(given, dict):
            given = next(iter(given.values()), "")
        if isinstance(family, dict):
            family = next(iter(family.values()), "")
        name = f"{given} {family}".strip() or None
        out.append(OjsAuthor(orcid=orcid, name=name, order=a.get("seq", idx)))
    out.sort(key=lambda x: x.order)
    return tuple(out)


def _localized(value) -> str:
    if isinstance(value, dict):
        return value.get("en") or next(iter(value.values()), "") or ""
    return value or ""


async def fetch_production_submissions(
    cfg: AuthConfig | None = None,
) -> list[OjsSubmission]:
    """Return OJS submissions currently in production stage.

    Skips submissions without a DOI (we need the DOI suffix as the manuscript
    primary key). Returns an empty list if OJS is not configured.
    """
    if _production_submissions_override is not None:
        return list(_production_submissions_override)

    global _production_cache
    now = time.monotonic()
    if _production_cache is not None:
        ts, cached = _production_cache
        if now - ts < _PRODUCTION_CACHE_TTL:
            return list(cached)

    cfg = cfg or get_config()
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        logger.info("OJS not configured; no production submissions available")
        return []

    url = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1/submissions"
    )
    headers = {"Authorization": f"Bearer {cfg.ojs_admin_token}"}

    found: list[OjsSubmission] = []
    offset = 0
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                params = [
                    ("stageIds[]", str(_STAGE_PRODUCTION)),
                    ("count", str(_PAGE_SIZE)),
                    ("offset", str(offset)),
                ]
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code in (401, 403):
                    raise OjsAdminTokenInvalid(
                        f"OJS rejected admin token ({resp.status_code}): {resp.text[:200]}"
                    )
                if resp.status_code >= 400:
                    raise OjsUnavailable(
                        f"OJS returned {resp.status_code}: {resp.text[:200]}"
                    )
                payload = resp.json()
                items = payload.get("items") or []
                items_max = payload.get("itemsMax") or 0
                for item in items:
                    parsed = _parse_submission(item, cfg.ojs_doi_prefix)
                    if parsed is not None:
                        found.append(parsed[0])
                offset += len(items)
                if not items or offset >= items_max:
                    break
    except httpx.RequestError as exc:
        raise OjsUnavailable(str(exc)) from exc

    logger.info("Fetched %d production submissions from OJS", len(found))
    _production_cache = (now, found)
    return list(found)


async def fetch_submission(
    submission_id: int, cfg: AuthConfig | None = None
) -> OjsSubmission | None:
    """Fetch a single submission with its author ORCIDs populated.

    Used by the import route so we don't have to re-list all production
    submissions (+N author fetches) to import one.
    """
    if _production_submissions_override is not None:
        for s in _production_submissions_override:
            if s.submission_id == submission_id:
                return s
        return None

    cfg = cfg or get_config()
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        return None

    base = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1"
    )
    headers = {"Authorization": f"Bearer {cfg.ojs_admin_token}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base}/submissions/{submission_id}", headers=headers
            )
            if resp.status_code in (401, 403):
                raise OjsAdminTokenInvalid(
                    f"OJS rejected admin token ({resp.status_code}): {resp.text[:200]}"
                )
            if resp.status_code == 404:
                return None
            if resp.status_code >= 400:
                raise OjsUnavailable(
                    f"OJS returned {resp.status_code}: {resp.text[:200]}"
                )
            parsed = _parse_submission(resp.json(), cfg.ojs_doi_prefix)
            if parsed is None:
                return None
            sub, publication_id = parsed
            publication = await _fetch_publication(
                client, cfg, sub.submission_id, publication_id, headers
            )
            if publication is not None:
                sub = _enrich_from_publication(sub, publication)
                issue_id = publication.get("issueId")
                if issue_id:
                    issue = await _fetch_issue(client, cfg, issue_id, headers)
                    if issue is not None:
                        sub = _enrich_from_issue(sub, issue)
            return sub
    except httpx.RequestError as exc:
        raise OjsUnavailable(str(exc)) from exc


def _enrich_from_publication(sub: OjsSubmission, publication: dict) -> OjsSubmission:
    authors = _parse_authors(publication)
    abstract = _localized(publication.get("abstract")) or None
    kws = publication.get("keywords") or {}
    if isinstance(kws, dict):
        kw_list = kws.get("en") or next(iter(kws.values()), []) or []
    else:
        kw_list = kws or []
    return replace(
        sub,
        authors=authors,
        abstract=abstract,
        keywords=tuple(kw_list),
    )


def _enrich_from_issue(sub: OjsSubmission, issue: dict) -> OjsSubmission:
    volume = issue.get("volume")
    number = issue.get("number")
    year = issue.get("year")
    return replace(
        sub,
        volume=str(volume) if volume is not None else None,
        issue_number=str(number) if number is not None else None,
        year=int(year) if year is not None else None,
    )


async def _fetch_publication(
    client: httpx.AsyncClient,
    cfg: AuthConfig,
    submission_id: int,
    publication_id: int,
    headers: dict,
) -> dict | None:
    url = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1/submissions/"
        f"{submission_id}/publications/{publication_id}"
    )
    try:
        resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.warning(
            "Failed to fetch publication for submission %s: %s", submission_id, exc
        )
        return None
    if resp.status_code >= 400:
        logger.warning(
            "OJS returned %s fetching publication %s: %s",
            resp.status_code,
            publication_id,
            resp.text[:200],
        )
        return None
    return resp.json()


async def _fetch_issue(
    client: httpx.AsyncClient,
    cfg: AuthConfig,
    issue_id: int,
    headers: dict,
) -> dict | None:
    url = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1/issues/{issue_id}"
    )
    try:
        resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("Failed to fetch issue %s: %s", issue_id, exc)
        return None
    if resp.status_code >= 400:
        logger.warning(
            "OJS returned %s fetching issue %s: %s",
            resp.status_code,
            issue_id,
            resp.text[:200],
        )
        return None
    return resp.json()


def _parse_submission(
    item: dict, doi_prefix: str
) -> tuple[OjsSubmission, int] | None:
    submission_id = item.get("id")
    publication = item.get("publications", [{}])[-1] if item.get("publications") else {}
    # Newer OJS versions expose `currentPublicationId`; fall back to the first
    # matching publication if needed.
    current_id = item.get("currentPublicationId")
    if current_id and item.get("publications"):
        for p in item["publications"]:
            if p.get("id") == current_id:
                publication = p
                break

    # OJS 3.3+ stores the DOI inside a nested doiObject; older versions used
    # `publication.doi` or `pub-id::doi`. Try all three.
    doi_object = publication.get("doiObject") or {}
    doi = (
        (doi_object.get("doi") if isinstance(doi_object, dict) else None)
        or publication.get("doi")
        or publication.get("pub-id::doi")
    )
    doi_suffix = _extract_doi_suffix(doi, doi_prefix)
    if not doi_suffix:
        logger.info(
            "Skipping OJS submission %s: no DOI (or not matching prefix %r)",
            submission_id,
            doi_prefix,
        )
        return None

    title = _localized(publication.get("fullTitle") or publication.get("title"))
    # Author list + abstract/keywords aren't embedded in the submissions-list
    # response; leave blank here and fill them in via a per-publication fetch.
    sub = OjsSubmission(
        submission_id=int(submission_id),
        doi_suffix=doi_suffix,
        title=title or doi_suffix,
        authors=(),
        doi=doi,
    )
    return sub, int(publication.get("id") or current_id)
