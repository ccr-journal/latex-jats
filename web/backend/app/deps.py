"""Shared FastAPI dependency callables.

Kept separate from main.py to avoid circular imports between routes and the app
factory. main.py sets _engine and _storage during the lifespan handler; route
modules import get_session and get_storage from here.
"""

from datetime import datetime
from typing import Generator, Literal, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, select

from . import ojs as ojs_client
from .models import (
    AccessToken,
    AuthorRead,
    CurrentUser,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptRead,
)
from .storage import Storage

_engine: Engine | None = None
_storage: Storage | None = None


def get_session() -> Generator[Session, None, None]:
    assert _engine is not None, "DB engine not initialized"
    with Session(_engine) as session:
        yield session


def get_storage() -> Storage:
    assert _storage is not None, "Storage not initialized"
    return _storage


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="Missing or malformed Authorization header")
    token = authorization.split(None, 1)[1].strip()
    row = session.exec(select(AccessToken).where(AccessToken.token == token)).first()
    if row is None:
        raise HTTPException(401, detail="Invalid session token")
    if row.expires_at is not None and row.expires_at < datetime.utcnow():
        session.delete(row)
        session.commit()
        raise HTTPException(401, detail="Session expired")
    return CurrentUser(orcid=row.orcid, name=row.name)


async def get_current_role(
    user: CurrentUser = Depends(get_current_user),
) -> Literal["editor", "author"]:
    try:
        editors = await ojs_client.fetch_editor_orcids()
    except (ojs_client.OjsAdminTokenInvalid, ojs_client.OjsUnavailable):
        # If we can't confirm editor status, fall back to author — safer default
        # (endpoints gated by require_editor will reject; author access still works).
        return "author"
    return "editor" if user.orcid in editors else "author"


async def require_editor(
    role: Literal["editor", "author"] = Depends(get_current_role),
) -> Literal["editor"]:
    if role != "editor":
        raise HTTPException(403, detail="Editor access required")
    return "editor"


def load_manuscript_for_user(
    doi_suffix: str,
    session: Session,
    user: CurrentUser,
    role: Literal["editor", "author"],
) -> Manuscript:
    """Return the manuscript if the current user may access it, else 404.

    Editors see everything. Authors see only manuscripts where their ORCID
    appears in ManuscriptAuthor. We return 404 (not 403) when an author is
    denied so we don't leak existence of other manuscripts.
    """
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if role == "editor":
        return ms
    link = session.exec(
        select(ManuscriptAuthor).where(
            ManuscriptAuthor.manuscript_id == doi_suffix,
            ManuscriptAuthor.orcid == user.orcid,
        )
    ).first()
    if link is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    return ms


def manuscript_to_read(
    ms: Manuscript, session: Session, storage: Storage | None = None
) -> ManuscriptRead:
    authors = session.exec(
        select(ManuscriptAuthor)
        .where(ManuscriptAuthor.manuscript_id == ms.doi_suffix)
        .order_by(ManuscriptAuthor.order)
    ).all()
    data = ms.model_dump()
    data["authors"] = [
        AuthorRead(orcid=a.orcid, name=a.name, order=a.order) for a in authors
    ]
    if storage is None:
        storage = _storage
    if storage is not None:
        source_dir = storage.source_dir(ms.doi_suffix)
        if source_dir.is_dir():
            data["upload_file_count"] = sum(
                1 for f in source_dir.rglob("*") if f.is_file()
            )
    return ManuscriptRead(**data)
