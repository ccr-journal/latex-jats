"""Conversion status polling route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..deps import get_session
from ..models import Manuscript, ManuscriptRead

router = APIRouter(prefix="/api/manuscripts", tags=["status"])


@router.get("/{doi_suffix}/status", response_model=ManuscriptRead)
def get_status(doi_suffix: str, session: Session = Depends(get_session)):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    return ms
