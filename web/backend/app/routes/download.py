"""Output zip download route."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..deps import get_session, get_storage
from ..models import Manuscript
from ..storage import Storage

router = APIRouter(prefix="/api/manuscripts", tags=["download"])


@router.get("/{doi_suffix}/download")
def download_output(
    doi_suffix: str,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

    zip_path = storage.output_zip(doi_suffix)
    if zip_path is None:
        raise HTTPException(404, detail="Output not yet available")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
