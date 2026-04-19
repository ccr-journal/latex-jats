"""FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlmodel import create_engine

from . import deps
from .models import (  # noqa: F401 — registers metadata
    AccessToken,
    Manuscript,
    ManuscriptAuthor,
)
from .routes import auth, download, manuscripts, ojs, output, status, upload
from .storage import Storage

_PROJECT_ROOT = Path(__file__).parents[3]
_STORAGE_ROOT = Path(os.environ.get("STORAGE_DIR", _PROJECT_ROOT / "storage"))
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{_STORAGE_ROOT / 'latex_jats.db'}"
)


_BACKEND_DIR = Path(__file__).parents[1]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _alembic_config(engine) -> AlembicConfig:
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return cfg


def _init_db_schema(engine) -> None:
    """Run `alembic upgrade head` on every startup.

    A fresh DB gets the full schema, an already-current DB is a no-op, and a
    DB that's behind gets caught up — so pulling a branch with a new
    migration "just works" without a manual alembic run.

    If the DB has tables but no alembic_version row (e.g. a dev DB from
    before migrations existed), refuse to touch it: we'd have to guess which
    revision the schema matches. Operator should stamp the correct revision
    then restart.
    """
    log = logging.getLogger("latex_jats.web")
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if tables and "alembic_version" not in tables:
        log.warning(
            "DB has tables but no alembic_version — skipping auto-upgrade. "
            "Run `alembic stamp <revision>` to bring it under migration "
            "control, then restart."
        )
        return

    alembic_command.upgrade(_alembic_config(engine), "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    _init_db_schema(engine)

    deps._engine = engine
    deps._storage = Storage(_STORAGE_ROOT)
    yield


app = FastAPI(title="LaTeX-JATS Web Service", lifespan=lifespan)

_CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
if _CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _CORS_ORIGINS.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(manuscripts.router)
app.include_router(upload.router)
app.include_router(status.router)
app.include_router(download.router)
app.include_router(output.router)
app.include_router(ojs.router)

# Serve frontend in production (dist/ built by Vite)
_FRONTEND_DIST = Path(__file__).parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
