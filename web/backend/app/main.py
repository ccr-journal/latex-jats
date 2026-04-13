"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, create_engine

from . import deps
from .models import AccessToken, Manuscript  # noqa: F401 — registers metadata
from .routes import download, manuscripts, status, upload
from .storage import Storage

_PROJECT_ROOT = Path(__file__).parents[3]
_DATABASE_URL = f"sqlite:///{_PROJECT_ROOT / 'storage' / 'latex_jats.db'}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    # Dev convenience: create tables if they don't exist.
    # In production, tables are created by `alembic upgrade head` before startup.
    SQLModel.metadata.create_all(engine)

    storage_root = _PROJECT_ROOT / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    deps._engine = engine
    deps._storage = Storage(storage_root)
    yield


app = FastAPI(title="LaTeX-JATS Web Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server; tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(manuscripts.router)
app.include_router(upload.router)
app.include_router(status.router)
app.include_router(download.router)
