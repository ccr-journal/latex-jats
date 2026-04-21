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

from .models import (
    AccessToken,
    AuthorRead,
    CurrentUser,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptRead,
    ManuscriptToken,
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


def _authenticate_bearer(authorization: str | None, session: Session) -> CurrentUser:
    """Validate a Bearer token and return the user. Raises HTTPException on failure.

    Tries editor session tokens (AccessToken) first, then per-manuscript author
    tokens (ManuscriptToken).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="Missing or malformed Authorization header")
    token = authorization.split(None, 1)[1].strip()

    # Try editor session token
    row = session.exec(select(AccessToken).where(AccessToken.token == token)).first()
    if row is not None:
        if row.expires_at is not None and row.expires_at < datetime.utcnow():
            session.delete(row)
            session.commit()
            raise HTTPException(401, detail="Session expired")
        return CurrentUser(username=row.username, name=row.name)

    # Try per-manuscript author token
    mt = session.exec(
        select(ManuscriptToken).where(ManuscriptToken.token == token)
    ).first()
    if mt is not None:
        return CurrentUser(name="Author", manuscript_token_scope=mt.manuscript_id)

    raise HTTPException(401, detail="Invalid session token")


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> CurrentUser:
    return _authenticate_bearer(authorization, session)


async def resolve_role(user: CurrentUser) -> Literal["editor", "author"]:
    """Determine role for a user (editor vs author).

    Manuscript-token sessions are always authors; any AccessToken session
    originates from EDITOR_CREDENTIALS login, so the role is editor.
    """
    if user.manuscript_token_scope is not None:
        return "author"
    return "editor"


async def get_current_role(
    user: CurrentUser = Depends(get_current_user),
) -> Literal["editor", "author"]:
    return await resolve_role(user)


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

    Editors see everything. Token-scoped authors see only their scoped
    manuscript. We return 404 (not 403) when denied so we don't leak
    existence of other manuscripts.
    """
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if role == "editor":
        return ms
    # Token-scoped author: must match the specific manuscript
    if user.manuscript_token_scope is not None:
        if user.manuscript_token_scope != doi_suffix:
            raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
        return ms
    # No valid access path for non-editor, non-token users
    raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")


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
        AuthorRead(
            name=a.name,
            email=a.email,
            order=a.order,
            primary_contact=a.primary_contact,
        )
        for a in authors
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
