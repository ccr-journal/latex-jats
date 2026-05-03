"""Site config: editor-edited journal-identity values (Issue #32).

GET is unauthenticated so the frontend can show the journal name in headers
before login. PUT is editor-only and sets ``configured_at`` on first save so
the dashboard can hide its first-run banner.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..deps import get_session, require_editor
from ..models import SiteConfig, SiteConfigRead, SiteConfigUpdate

router = APIRouter(prefix="/api/site-config", tags=["site-config"])


def _get_singleton(session: Session) -> SiteConfig:
    row = session.get(SiteConfig, 1)
    if row is None:
        raise HTTPException(500, detail="SiteConfig row missing")
    return row


@router.get("", response_model=SiteConfigRead)
def get_site_config_endpoint(session: Session = Depends(get_session)):
    return _get_singleton(session)


@router.put("", response_model=SiteConfigRead)
def update_site_config(
    body: SiteConfigUpdate,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    row = _get_singleton(session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    now = datetime.utcnow()
    row.updated_at = now
    if row.configured_at is None:
        row.configured_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
