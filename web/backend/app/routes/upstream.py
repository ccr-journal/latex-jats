"""Upstream source linkage routes (Issue #7).

Endpoints for linking a manuscript to a git/Overleaf/GitHub remote and pulling
updates into the manuscript's source_dir without requiring the author to
download + re-upload.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from urllib.parse import urlparse

from .. import upstream as upstream_module
from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    get_storage,
    load_manuscript_for_user,
    manuscript_to_read,
)
from ..models import CurrentUser, ManuscriptRead, ManuscriptStatus
from ..storage import Storage

logger = logging.getLogger("jatsmith.web.upstream")

router = APIRouter(prefix="/api/manuscripts", tags=["upstream"])


_ALLOWED_SCHEMES = {"http", "https", "ssh", "git"}


class UpstreamUpdate(BaseModel):
    url: str
    token: str | None = None        # null → leave existing token untouched
    clear_token: bool = False       # explicit delete (ignored if token is set)
    ref: str | None = None
    subpath: str | None = None
    main_file: str | None = None


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme == upstream_module.UPLOAD_URL_SCHEME:
        raise HTTPException(400, detail="file:// URLs are reserved for uploaded sources")
    if scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            400, detail=f"Unsupported URL scheme '{scheme}' (allowed: {sorted(_ALLOWED_SCHEMES)})"
        )
    if not parsed.hostname and scheme != "ssh":
        raise HTTPException(400, detail="URL is missing a host")


@router.put("/{doi_suffix}/upstream", response_model=ManuscriptRead)
def put_upstream(
    doi_suffix: str,
    body: UpstreamUpdate,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Link the manuscript to an external git URL (or replace the existing link).

    Wipes any existing source files and resets the manuscript to ``draft``.
    Otherwise an editor could press "Re-run conversion" between linking and
    syncing and accidentally process the previous upload — see Issue #7
    discussion. The companion sync endpoint (or the frontend's link+sync
    chain) is what actually fetches the new source.
    """
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    _validate_url(body.url)

    if ms.status in (ManuscriptStatus.queued, ManuscriptStatus.processing):
        raise HTTPException(
            409, detail="A conversion is in progress; wait for it to finish before re-linking."
        )

    source_dir = storage.source_dir(doi_suffix)
    if source_dir.exists():
        shutil.rmtree(source_dir)

    ms.upstream_url = body.url
    ms.upstream_ref = body.ref or None
    ms.upstream_subpath = body.subpath or None
    if body.main_file is not None:
        ms.main_file = body.main_file or None

    if body.token:
        ms.upstream_token_encrypted = upstream_module.encrypt_token(body.token)
    elif body.clear_token:
        ms.upstream_token_encrypted = None

    # Reset to "no source yet" — sync will populate it.
    ms.status = ManuscriptStatus.draft
    ms.uploaded_at = None
    ms.uploaded_by = None
    ms.last_synced_at = None
    ms.last_synced_sha = None
    ms.job_log = ""
    ms.job_started_at = None
    ms.job_completed_at = None
    ms.pipeline_steps = None
    ms.updated_at = datetime.utcnow()

    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.delete("/{doi_suffix}/upstream", response_model=ManuscriptRead)
def delete_upstream(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Clear external upstream link AND wipe the synced source files.

    Unlinking feels like "start over from nothing" — leaving the last synced
    files around was surprising because the editor could still press
    Re-run conversion on source they thought they had thrown away.

    No-op for upload-sourced manuscripts (defensive — the frontend doesn't
    surface an Unlink button in that state).
    """
    ms = load_manuscript_for_user(doi_suffix, session, user, role)

    if ms.status in (ManuscriptStatus.queued, ManuscriptStatus.processing):
        raise HTTPException(
            409, detail="A conversion is in progress; wait for it to finish before unlinking."
        )

    was_external = bool(
        ms.upstream_url and not upstream_module.is_upload_url(ms.upstream_url)
    )
    if was_external:
        source_dir = storage.source_dir(doi_suffix)
        if source_dir.exists():
            shutil.rmtree(source_dir)
        ms.upstream_url = None
        ms.uploaded_at = None
        ms.uploaded_by = None
        ms.status = ManuscriptStatus.draft
        ms.job_log = ""
        ms.job_started_at = None
        ms.job_completed_at = None
        ms.pipeline_steps = None

    ms.upstream_token_encrypted = None
    ms.upstream_ref = None
    ms.upstream_subpath = None
    ms.last_synced_at = None
    ms.last_synced_sha = None
    ms.updated_at = datetime.utcnow()
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.post("/{doi_suffix}/upstream/sync", response_model=ManuscriptRead)
def sync_upstream(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Fetch the upstream repo into source_dir.

    Leaves the manuscript in ``uploaded`` status so the caller can review the
    fetched files and tick options (fix-source, canonical ccr.cls, main_file)
    before pressing "Start conversion" on the usual /process endpoint.
    """
    ms = load_manuscript_for_user(doi_suffix, session, user, role)

    if ms.status in (ManuscriptStatus.queued, ManuscriptStatus.processing):
        raise HTTPException(
            409, detail="A conversion is already in progress for this manuscript"
        )
    if not ms.upstream_url:
        raise HTTPException(400, detail="No upstream URL linked — set one first")
    if upstream_module.is_upload_url(ms.upstream_url):
        raise HTTPException(
            400, detail="Manuscript source was uploaded directly; there is nothing to sync."
        )

    storage.ensure_dirs(doi_suffix)
    source_dir = storage.source_dir(doi_suffix)

    try:
        sha = upstream_module.fetch_upstream(ms, source_dir)
    except upstream_module.UpstreamError as exc:
        logger.warning("Upstream sync failed for %s: %s", doi_suffix, exc)
        raise HTTPException(502, detail=str(exc))

    now = datetime.utcnow()
    ms.uploaded_at = now
    ms.uploaded_by = "upstream"
    ms.status = ManuscriptStatus.uploaded
    ms.last_synced_at = now
    ms.last_synced_sha = sha
    ms.job_log = ""
    ms.job_started_at = None
    ms.job_completed_at = None
    ms.pipeline_steps = None  # cleared so the previous run's results don't linger
    ms.updated_at = now
    session.add(ms)
    session.commit()
    session.refresh(ms)

    return manuscript_to_read(ms, session)
