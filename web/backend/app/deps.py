"""Shared FastAPI dependency callables.

Kept separate from main.py to avoid circular imports between routes and the app
factory. main.py sets _engine and _storage during the lifespan handler; route
modules import get_session and get_storage from here.
"""

from datetime import datetime
from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, select

from .models import AccessToken, CurrentUser
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
