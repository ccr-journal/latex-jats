"""FastAPI application factory."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

from . import deps
from .models import (  # noqa: F401 — registers metadata
    AccessToken,
    LoginState,
    Manuscript,
)
from .routes import auth, download, manuscripts, output, status, upload
from .storage import Storage

_PROJECT_ROOT = Path(__file__).parents[3]
_STORAGE_ROOT = Path(os.environ.get("STORAGE_DIR", _PROJECT_ROOT / "storage"))
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{_STORAGE_ROOT / 'latex_jats.db'}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    # Dev convenience: create tables if they don't exist.
    # In production, tables are created by `alembic upgrade head` before startup.
    SQLModel.metadata.create_all(engine)

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

# Serve frontend in production (dist/ built by Vite)
_FRONTEND_DIST = Path(__file__).parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
