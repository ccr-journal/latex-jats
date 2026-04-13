"""Source file upload route."""

import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from .. import deps
from ..deps import get_session, get_storage
from ..models import ManuscriptRead, ManuscriptStatus, Manuscript
from ..storage import Storage
from ..worker import run_pipeline

router = APIRouter(prefix="/api/manuscripts", tags=["upload"])


def _safe_extract_zip(data: bytes, dest: Path) -> None:
    """Extract a zip archive into dest, guarding against zip-slip attacks.

    Preserves relative subdirectory structure (needed by the pipeline) but
    drops any path components that would escape the destination directory.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            # Resolve the target path and reject anything outside dest
            target = (dest / member).resolve()
            if not target.is_relative_to(dest.resolve()):
                continue
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))


@router.post("/{doi_suffix}/upload", response_model=ManuscriptRead, status_code=201)
async def upload_source(
    doi_suffix: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    uploaded_by: str = Form("editor"),
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

    for upload in files:
        content = await upload.read()
        filename = Path(upload.filename or "upload").name
        if filename.endswith(".zip"):
            _safe_extract_zip(content, source_dir)
        else:
            (source_dir / filename).write_bytes(content)

    now = datetime.utcnow()
    ms.uploaded_at = now
    ms.uploaded_by = uploaded_by
    ms.updated_at = now
    ms.status = ManuscriptStatus.queued
    session.add(ms)
    session.commit()
    session.refresh(ms)

    background_tasks.add_task(run_pipeline, doi_suffix, deps._engine, storage)

    return ms
