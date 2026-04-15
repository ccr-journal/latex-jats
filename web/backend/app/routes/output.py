"""Serve individual files from conversion output (HTML proof, CSS, images)."""

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..deps import get_current_user, get_session, get_storage
from ..models import CurrentUser, Manuscript
from ..storage import Storage

router = APIRouter(prefix="/api/manuscripts", tags=["output"])


@router.get("/{doi_suffix}/output/{path:path}")
def get_output_file(
    doi_suffix: str,
    path: str,
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

    output_dir = storage.convert_output_dir(doi_suffix)
    file_path = (output_dir / path).resolve()

    # Guard against path traversal
    if not file_path.is_relative_to(output_dir.resolve()):
        raise HTTPException(404, detail="File not found")

    if not file_path.is_file():
        raise HTTPException(404, detail="File not found")

    media_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(file_path, media_type=media_type)
