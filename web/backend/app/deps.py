"""Shared FastAPI dependency callables.

Kept separate from main.py to avoid circular imports between routes and the app
factory. main.py sets _engine and _storage during the lifespan handler; route
modules import get_session and get_storage from here.
"""

from typing import Generator

from sqlalchemy import Engine
from sqlmodel import Session

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
