"""FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlmodel import create_engine

from datetime import datetime

from sqlmodel import Session, select

from . import deps
from .models import (  # noqa: F401 — registers metadata
    AccessToken,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptStatus,
    PIPELINE_STEPS,
    StepStatus,
)
from .routes import auth, download, manuscripts, ojs, output, status, upload, upstream
from .storage import Storage

_PROJECT_ROOT = Path(__file__).parents[3]
_STORAGE_ROOT = Path(os.environ.get("STORAGE_DIR", _PROJECT_ROOT / "storage"))
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{_STORAGE_ROOT / 'jatsmith.db'}"
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
    log = logging.getLogger("jatsmith.web")
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


def _reset_orphaned_jobs(engine) -> None:
    """Mark any in-flight pipeline jobs as failed at startup.

    A manuscript with status ``queued`` or ``processing`` can only reach this
    point if the previous server process died mid-pipeline (reload, crash,
    Ctrl-C). The BackgroundTask is gone, so the row is wedged — the
    ``/process`` endpoint refuses to restart while status is in that set.
    Flip them to ``failed`` so the editor can retry.
    """
    log = logging.getLogger("jatsmith.web")
    stuck_statuses = (ManuscriptStatus.queued, ManuscriptStatus.processing)
    with Session(engine) as session:
        orphans = session.exec(
            select(Manuscript).where(Manuscript.status.in_(stuck_statuses))
        ).all()
        if not orphans:
            return
        now = datetime.utcnow()
        for ms in orphans:
            if ms.pipeline_steps:
                steps = [dict(s) for s in ms.pipeline_steps]
                hit_running = False
                for step in steps:
                    if step.get("status") == StepStatus.running:
                        step["status"] = StepStatus.failed
                        step["completed_at"] = now.isoformat()
                        hit_running = True
                    elif hit_running and step.get("status") == StepStatus.pending:
                        step["status"] = StepStatus.skipped
                ms.pipeline_steps = steps
            note = "ERROR: server restarted while job was running; marking as failed"
            ms.job_log = (ms.job_log + "\n" + note) if ms.job_log else note
            ms.status = ManuscriptStatus.failed
            ms.job_completed_at = now
            ms.updated_at = now
            session.add(ms)
        session.commit()
        log.warning(
            "Reset %d orphaned job(s) to failed: %s",
            len(orphans),
            ", ".join(ms.doi_suffix for ms in orphans),
        )


def _migrate_legacy_db_filename() -> None:
    """Rename storage/latex_jats.db → storage/jatsmith.db on first startup
    after the project rename. Only fires when DATABASE_URL is unset (default
    sqlite path) and the new file does not exist yet.
    """
    if "DATABASE_URL" in os.environ:
        return
    new = _STORAGE_ROOT / "jatsmith.db"
    old = _STORAGE_ROOT / "latex_jats.db"
    if old.exists() and not new.exists():
        old.rename(new)
        logging.getLogger("jatsmith.web").info(
            "Renamed legacy database file %s → %s", old.name, new.name
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_db_filename()

    engine = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    _init_db_schema(engine)
    _reset_orphaned_jobs(engine)

    deps._engine = engine
    deps._storage = Storage(_STORAGE_ROOT)
    yield


app = FastAPI(title="JATSmith Web Service", lifespan=lifespan)

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

@app.get("/api/version")
def get_version() -> dict[str, str]:
    from jatsmith.ccr_cls import EXPECTED_CCR_CLS_VERSION
    return {
        "version": pkg_version("jatsmith"),
        "ccr_cls_version": EXPECTED_CCR_CLS_VERSION,
    }


app.include_router(auth.router)
app.include_router(manuscripts.router)
app.include_router(upload.router)
app.include_router(upstream.router)
app.include_router(status.router)
app.include_router(download.router)
app.include_router(output.router)
app.include_router(ojs.router)

# Serve frontend in production (dist/ built by Vite)
_FRONTEND_DIST = Path(__file__).parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
