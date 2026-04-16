"""Manuscript CRUD routes."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    load_manuscript_for_user,
    manuscript_to_read,
    require_editor,
)
from ..models import (
    CurrentUser,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptCreate,
    ManuscriptRead,
)

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.get("", response_model=list[ManuscriptRead])
def list_manuscripts(
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    if role == "editor":
        manuscripts = session.exec(
            select(Manuscript).order_by(Manuscript.created_at.desc())
        ).all()
    else:
        manuscripts = session.exec(
            select(Manuscript)
            .join(ManuscriptAuthor, ManuscriptAuthor.manuscript_id == Manuscript.doi_suffix)
            .where(ManuscriptAuthor.orcid == user.orcid)
            .order_by(Manuscript.created_at.desc())
        ).all()
    return [manuscript_to_read(ms, session) for ms in manuscripts]


@router.post("", response_model=ManuscriptRead, status_code=201)
def create_manuscript(
    body: ManuscriptCreate,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    existing = session.get(Manuscript, body.doi_suffix)
    if existing:
        raise HTTPException(409, detail=f"Manuscript '{body.doi_suffix}' already exists")
    ms = Manuscript(**body.model_dump())
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


class ManuscriptUpdate(SQLModel):
    fix_source: bool | None = None


@router.patch("/{doi_suffix}", response_model=ManuscriptRead)
def update_manuscript(
    doi_suffix: str,
    body: ManuscriptUpdate,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    if body.fix_source is not None:
        ms.fix_source = body.fix_source
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.get("/{doi_suffix}", response_model=ManuscriptRead)
def get_manuscript(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    return manuscript_to_read(ms, session)
