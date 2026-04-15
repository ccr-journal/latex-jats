"""Manuscript CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import get_current_user, get_session
from ..models import CurrentUser, Manuscript, ManuscriptCreate, ManuscriptRead

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.get("", response_model=list[ManuscriptRead])
def list_manuscripts(
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Manuscript).order_by(Manuscript.created_at.desc())
    ).all()


@router.post("", response_model=ManuscriptRead, status_code=201)
def create_manuscript(
    body: ManuscriptCreate,
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    existing = session.get(Manuscript, body.doi_suffix)
    if existing:
        raise HTTPException(409, detail=f"Manuscript '{body.doi_suffix}' already exists")
    ms = Manuscript(**body.model_dump())
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return ms


@router.get("/{doi_suffix}", response_model=ManuscriptRead)
def get_manuscript(
    doi_suffix: str,
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    return ms
