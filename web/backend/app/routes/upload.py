"""Source file upload route."""

import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from .. import deps
from ..deps import get_current_user, get_session, get_storage
from ..models import CurrentUser, ManuscriptRead, ManuscriptStatus, Manuscript
from ..storage import Storage
from ..worker import run_pipeline, init_pipeline_steps

router = APIRouter(prefix="/api/manuscripts", tags=["upload"])


def _safe_extract_zip(data: bytes, dest: Path) -> None:
    """Extract a zip archive into dest, guarding against zip-slip attacks.

    If the zip contains a single top-level directory that wraps all files,
    that directory is stripped so files land directly in dest.  Preserves
    relative subdirectory structure otherwise.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]

        # Detect single top-level directory wrapper
        prefix = ""
        top_dirs = {n.split("/")[0] for n in names if "/" in n}
        root_files = [n for n in names if "/" not in n]
        if len(top_dirs) == 1 and not root_files:
            prefix = top_dirs.pop() + "/"

        for member in zf.namelist():
            # Strip the single wrapper directory if present
            rel = member[len(prefix):] if prefix and member.startswith(prefix) else member
            if not rel or rel.endswith("/"):
                continue
            target = (dest / rel).resolve()
            if not target.is_relative_to(dest.resolve()):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))


@router.post("/{doi_suffix}/upload", response_model=ManuscriptRead, status_code=201)
async def upload_source(
    doi_suffix: str,
    files: list[UploadFile] = File(...),
    uploaded_by: str = Form("editor"),
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

    if ms.status in (ManuscriptStatus.queued, ManuscriptStatus.processing):
        raise HTTPException(
            409, detail="A conversion is already in progress for this manuscript"
        )

    source_dir = storage.source_dir(doi_suffix)
    source_dir.mkdir(parents=True, exist_ok=True)

    # Collect non-zip uploads so we can strip a common top-level folder if present
    plain_uploads: list[tuple[str, bytes]] = []
    for upload in files:
        content = await upload.read()
        raw = upload.filename or "upload"
        if Path(raw).name.endswith(".zip"):
            _safe_extract_zip(content, source_dir)
        else:
            plain_uploads.append((raw, content))

    # If every plain upload sits inside the same top-level directory, strip it
    # (so a folder like "mypaper/main.tex" lands as "main.tex" in source_dir)
    prefix = ""
    if plain_uploads:
        top_dirs = {p.split("/", 1)[0] for p, _ in plain_uploads if "/" in p}
        has_root_file = any("/" not in p for p, _ in plain_uploads)
        if len(top_dirs) == 1 and not has_root_file:
            prefix = top_dirs.pop() + "/"

    source_root = source_dir.resolve()
    for raw, content in plain_uploads:
        rel = raw[len(prefix):] if prefix and raw.startswith(prefix) else raw
        target = (source_dir / rel).resolve()
        # Guard against path traversal (e.g. "../escape.txt")
        if not target.is_relative_to(source_root):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    now = datetime.utcnow()
    ms.uploaded_at = now
    ms.uploaded_by = "editor"
    ms.updated_at = now
    ms.status = ManuscriptStatus.uploaded
    ms.job_log = ""
    ms.job_started_at = None
    ms.job_completed_at = None
    ms.pipeline_steps = None  # cleared so the previous run's results don't linger
    session.add(ms)
    session.commit()
    session.refresh(ms)

    return ms


@router.post("/{doi_suffix}/process", response_model=ManuscriptRead)
async def start_processing(
    doi_suffix: str,
    background_tasks: BackgroundTasks,
    fix: bool = Form(False),
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Start the conversion pipeline on previously uploaded source."""
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

    if ms.status in (ManuscriptStatus.queued, ManuscriptStatus.processing):
        raise HTTPException(
            409, detail="A conversion is already in progress for this manuscript"
        )

    if ms.uploaded_at is None:
        raise HTTPException(
            400, detail="No source files uploaded yet — upload before starting processing"
        )

    ms.status = ManuscriptStatus.queued
    ms.job_log = ""
    ms.job_started_at = None
    ms.job_completed_at = None
    ms.pipeline_steps = init_pipeline_steps()
    ms.updated_at = datetime.utcnow()
    session.add(ms)
    session.commit()
    session.refresh(ms)

    background_tasks.add_task(run_pipeline, doi_suffix, deps._engine, storage, fix=fix)

    return ms
