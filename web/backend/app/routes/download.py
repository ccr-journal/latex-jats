"""Output zip download route."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    get_storage,
    load_manuscript_for_user,
)
from ..models import CurrentUser
from ..storage import Storage

router = APIRouter(prefix="/api/manuscripts", tags=["download"])


@router.get("/{doi_suffix}/download")
def download_output(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    load_manuscript_for_user(doi_suffix, session, user, role)

    zip_path = storage.output_zip(doi_suffix)
    if zip_path is None:
        raise HTTPException(404, detail="Output not yet available")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
