"""OJS REST client.

Used for submission listing (see fetch_production_submissions) — the "create
manuscript" picker in the frontend fetches submissions in a caller-selected
OJS stage (default copyediting, stageId 4; production, stageId 5, is used
for backlog import) with their DOI suffix and author names. Also used to
push metadata updates (title, abstract, keywords, authors) back to OJS after
conversion.

The backend holds a journal-admin OJS API token in `OJS_ADMIN_TOKEN`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace

import httpx

from .config import AuthConfig, get_config

logger = logging.getLogger("latex_jats.web.ojs")

_STAGE_COPYEDITING = 4
_STAGE_PRODUCTION = 5
_PAGE_SIZE = 100


@dataclass(frozen=True)
class OjsAuthor:
    name: str | None = None
    email: str | None = None
    order: int = 0


@dataclass(frozen=True)
class OjsSubmission:
    submission_id: int
    doi_suffix: str
    title: str
    subtitle: str | None = None
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


# ── Production submissions ────────────────────────────────────────────────────

# Test hook: when non-None, fetch_production_submissions returns this directly
# without making an HTTP request. Set in tests that need canned data.
_production_submissions_override: list[OjsSubmission] | None = None

# Short in-process cache for the (slow) production submissions list so the
# picker reopens instantly. Editors importing a submission see it disappear
# from the list on next open; a 60s TTL keeps the window small. Keyed by
# stage so switching stages in the picker doesn't trash the other stage's
# entry.
_production_cache: dict[int, tuple[float, list[OjsSubmission]]] = {}
_PRODUCTION_CACHE_TTL = 60.0


def set_production_submissions_override(subs: list[OjsSubmission] | None) -> None:
    global _production_submissions_override
    _production_submissions_override = subs
    _production_cache.clear()


def invalidate_production_cache() -> None:
    _production_cache.clear()


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
        given = (a.get("givenName") or {}).get("en") or a.get("givenName") or ""
        family = (a.get("familyName") or {}).get("en") or a.get("familyName") or ""
        if isinstance(given, dict):
            given = next(iter(given.values()), "")
        if isinstance(family, dict):
            family = next(iter(family.values()), "")
        name = f"{given} {family}".strip() or None
        email = a.get("email") or None
        out.append(OjsAuthor(name=name, email=email, order=a.get("seq", idx)))
    out.sort(key=lambda x: x.order)
    return tuple(out)


def _localized(value) -> str:
    if isinstance(value, dict):
        return value.get("en") or next(iter(value.values()), "") or ""
    return value or ""


async def fetch_production_submissions(
    cfg: AuthConfig | None = None,
    stage_id: int = _STAGE_COPYEDITING,
) -> list[OjsSubmission]:
    """Return OJS submissions currently in the given stage.

    Defaults to copyediting (stageId 4); pass `_STAGE_PRODUCTION` (5) to list
    backlog/published items. Skips submissions without a DOI (we need the DOI
    suffix as the manuscript primary key). Returns an empty list if OJS is
    not configured.
    """
    if _production_submissions_override is not None:
        return list(_production_submissions_override)

    now = time.monotonic()
    cached_entry = _production_cache.get(stage_id)
    if cached_entry is not None:
        ts, cached = cached_entry
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
                    ("stageIds[]", str(stage_id)),
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

    logger.info(
        "Fetched %d submissions from OJS stage %d", len(found), stage_id
    )
    _production_cache[stage_id] = (now, found)
    return list(found)


async def fetch_submission(
    submission_id: int, cfg: AuthConfig | None = None
) -> OjsSubmission | None:
    """Fetch a single submission with its author list populated.

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


async def is_submission_in_production(
    submission_id: int, cfg: AuthConfig | None = None
) -> bool:
    """Check whether an OJS submission has moved to production stage (stageId 5)."""
    cfg = cfg or get_config()
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        return False

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
            if resp.status_code >= 400:
                raise OjsUnavailable(
                    f"OJS returned {resp.status_code}: {resp.text[:200]}"
                )
            return resp.json().get("stageId") == _STAGE_PRODUCTION
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


async def update_publication_field(
    submission_id: int,
    field: str,
    latex_value: str | list[str],
    cfg: AuthConfig | None = None,
) -> None:
    """Push a single metadata field from the LaTeX/JATS output to OJS.

    Supported fields: title, abstract, keywords.  Authors are handled
    separately via ``update_publication_authors``.
    """
    if field not in ("title", "subtitle", "abstract", "keywords"):
        raise ValueError(f"Unsupported field for OJS update: {field!r}")

    cfg = cfg or get_config()
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        raise OjsUnavailable("OJS not configured")

    base = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1"
    )
    headers = {"Authorization": f"Bearer {cfg.ojs_admin_token}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Fetch submission to get the current publication ID
            resp = await client.get(
                f"{base}/submissions/{submission_id}", headers=headers
            )
            if resp.status_code >= 400:
                raise OjsUnavailable(
                    f"OJS returned {resp.status_code} fetching submission: {resp.text[:200]}"
                )
            parsed = _parse_submission(resp.json(), cfg.ojs_doi_prefix)
            if parsed is None:
                raise OjsUnavailable(f"Could not parse submission {submission_id}")
            _, publication_id = parsed

            # Build the PUT payload
            if field == "title":
                payload = {"title": {"en": latex_value}}
            elif field == "subtitle":
                payload = {"subtitle": {"en": latex_value or ""}}
            elif field == "abstract":
                payload = {"abstract": {"en": latex_value}}
            elif field == "keywords":
                payload = {"keywords": {"en": latex_value}}

            # OJS accepts auth via Bearer header or apiToken query param;
            # some configurations only grant write access via apiToken.
            resp = await client.put(
                f"{base}/submissions/{submission_id}/publications/{publication_id}",
                params={"apiToken": cfg.ojs_admin_token},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code == 401:
                raise OjsAdminTokenInvalid(
                    f"OJS rejected token for PUT: {resp.text[:200]}"
                )
            if resp.status_code == 403:
                raise OjsUnavailable(
                    "OJS refused the update — the publication may already be published"
                )
            if resp.status_code >= 400:
                raise OjsUnavailable(
                    f"OJS returned {resp.status_code} updating publication: {resp.text[:200]}"
                )
    except httpx.RequestError as exc:
        raise OjsUnavailable(str(exc)) from exc

    logger.info(
        "Updated OJS publication field %r for submission %s", field, submission_id
    )


async def update_publication_authors(
    submission_id: int,
    latex_authors: list[str],
    cfg: AuthConfig | None = None,
) -> None:
    """Update author names in an OJS publication to match LaTeX output.

    Fetches the current publication authors, matches by position, and updates
    names for mismatched entries.  Preserves OJS author IDs, affiliations,
    and other fields.
    """
    cfg = cfg or get_config()
    if not cfg.ojs_admin_token or not cfg.ojs_base_url:
        raise OjsUnavailable("OJS not configured")

    base = (
        f"{cfg.ojs_base_url.rstrip('/')}"
        f"/index.php/{cfg.ojs_journal_path}/api/v1"
    )
    headers = {
        "Authorization": f"Bearer {cfg.ojs_admin_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get submission + publication ID
            resp = await client.get(
                f"{base}/submissions/{submission_id}", headers=headers
            )
            if resp.status_code >= 400:
                raise OjsUnavailable(
                    f"OJS returned {resp.status_code}: {resp.text[:200]}"
                )
            parsed = _parse_submission(resp.json(), cfg.ojs_doi_prefix)
            if parsed is None:
                raise OjsUnavailable(f"Could not parse submission {submission_id}")
            _, publication_id = parsed

            # Fetch current publication to get existing author records
            publication = await _fetch_publication(
                client, cfg, submission_id, publication_id, headers
            )
            if publication is None:
                raise OjsUnavailable("Could not fetch publication for author update")

            ojs_authors = publication.get("authors") or []
            # Update names by position for as many as we can match
            for i, latex_name in enumerate(latex_authors):
                if i >= len(ojs_authors):
                    break
                author = ojs_authors[i]
                # Split LaTeX "Given Family" into given/family names
                parts = latex_name.rsplit(" ", 1)
                given = parts[0] if len(parts) > 1 else latex_name
                family = parts[1] if len(parts) > 1 else ""

                author_id = author.get("id")
                if author_id is None:
                    continue

                resp = await client.put(
                    f"{base}/submissions/{submission_id}/publications/{publication_id}",
                    headers=headers,
                    json={
                        "authors": [
                            {
                                **a,
                                **(
                                    {
                                        "givenName": {"en": given},
                                        "familyName": {"en": family},
                                    }
                                    if a.get("id") == author_id
                                    else {}
                                ),
                            }
                            for a in ojs_authors
                        ]
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Failed to update author %d for submission %s: %s",
                        i, submission_id, resp.text[:200],
                    )
    except httpx.RequestError as exc:
        raise OjsUnavailable(str(exc)) from exc

    logger.info("Updated OJS authors for submission %s", submission_id)


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

    title = _localized(publication.get("title"))
    subtitle = _localized(publication.get("subtitle")) or None
    # Fall back to fullTitle if title is empty (older OJS)
    if not title:
        title = _localized(publication.get("fullTitle"))
    # Author list + abstract/keywords aren't embedded in the submissions-list
    # response; leave blank here and fill them in via a per-publication fetch.
    sub = OjsSubmission(
        submission_id=int(submission_id),
        doi_suffix=doi_suffix,
        title=title or doi_suffix,
        subtitle=subtitle,
        authors=(),
        doi=doi,
    )
    return sub, int(publication.get("id") or current_id)
