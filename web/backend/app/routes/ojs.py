"""OJS integration routes — production submission picker + import."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from .. import ojs as ojs_client
from ..deps import get_session, manuscript_to_read, require_editor
from ..models import (
    AuthorRead,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptRead,
)

logger = logging.getLogger("latex_jats.web.ojs_routes")

router = APIRouter(prefix="/api/ojs", tags=["ojs"])


class OjsSubmissionRead(BaseModel):
    submission_id: int
    doi_suffix: str
    title: str
    authors: list[AuthorRead]
    already_imported: bool


@router.get("/submissions", response_model=list[OjsSubmissionRead])
async def list_production_submissions(
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    try:
        subs = await ojs_client.fetch_production_submissions()
    except ojs_client.OjsAdminTokenInvalid as exc:
        logger.error("OJS admin token invalid: %s", exc)
        raise HTTPException(502, detail="OJS admin token invalid")
    except ojs_client.OjsUnavailable as exc:
        logger.error("OJS unavailable: %s", exc)
        raise HTTPException(502, detail="OJS unavailable")

    out: list[OjsSubmissionRead] = []
    for s in subs:
        existing = session.get(Manuscript, s.doi_suffix)
        out.append(
            OjsSubmissionRead(
                submission_id=s.submission_id,
                doi_suffix=s.doi_suffix,
                title=s.title,
                authors=[
                    AuthorRead(orcid=a.orcid, name=a.name, order=a.order)
                    for a in s.authors
                ],
                already_imported=existing is not None,
            )
        )
    return out


@router.post(
    "/submissions/{submission_id}/import",
    response_model=ManuscriptRead,
    status_code=201,
)
async def import_submission(
    submission_id: int,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    try:
        target = await ojs_client.fetch_submission(submission_id)
    except ojs_client.OjsAdminTokenInvalid as exc:
        raise HTTPException(502, detail=str(exc))
    except ojs_client.OjsUnavailable as exc:
        raise HTTPException(502, detail=str(exc))

    if target is None:
        raise HTTPException(
            404,
            detail=f"OJS submission {submission_id} not found",
        )

    if session.get(Manuscript, target.doi_suffix):
        raise HTTPException(
            409,
            detail=f"Manuscript '{target.doi_suffix}' already exists",
        )

    now = datetime.utcnow()
    ms = Manuscript(
        doi_suffix=target.doi_suffix,
        ojs_submission_id=target.submission_id,
        title=target.title or None,
        subtitle=target.subtitle,
        abstract=target.abstract,
        keywords=list(target.keywords) if target.keywords else None,
        doi=target.doi,
        volume=target.volume,
        issue_number=target.issue_number,
        year=target.year,
        created_at=now,
        updated_at=now,
    )
    session.add(ms)
    for a in target.authors:
        session.add(
            ManuscriptAuthor(
                manuscript_id=target.doi_suffix,
                orcid=a.orcid,
                name=a.name,
                email=a.email,
                order=a.order,
            )
        )
    session.commit()
    session.refresh(ms)
    ojs_client.invalidate_production_cache()
    return manuscript_to_read(ms, session)
