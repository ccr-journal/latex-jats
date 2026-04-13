"""Source file upload route."""

import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from ..deps import get_session, get_storage
from ..models import ConversionJob, JobRead, Manuscript
from ..storage import Storage

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


@router.post("/{doi_suffix}/upload", response_model=JobRead, status_code=201)
async def upload_source(
    doi_suffix: str,
    files: list[UploadFile] = File(...),
    uploaded_by: str = Form("editor"),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

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
    session.add(ms)

    job = ConversionJob(manuscript_id=doi_suffix)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
