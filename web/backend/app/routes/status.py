"""Conversion status polling route."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    load_manuscript_for_user,
    manuscript_to_read,
)
from ..models import CurrentUser, ManuscriptRead

router = APIRouter(prefix="/api/manuscripts", tags=["status"])


@router.get("/{doi_suffix}/status", response_model=ManuscriptRead)
def get_status(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    return manuscript_to_read(ms, session)
