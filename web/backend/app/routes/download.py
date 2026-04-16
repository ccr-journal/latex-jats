"""Output zip download route."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..deps import (
    _authenticate_bearer,
    get_session,
    get_storage,
    load_manuscript_for_user,
    resolve_role,
)
from ..presign import verify_token
from ..storage import Storage

router = APIRouter(prefix="/api/manuscripts", tags=["download"])


@router.get("/{doi_suffix}/download")
async def download_output(
    doi_suffix: str,
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    if token is not None:
        orcid = verify_token(token, doi_suffix)
        if orcid is None:
            raise HTTPException(401, detail="Invalid or expired presign token")
    else:
        user = _authenticate_bearer(authorization, session)
        role = await resolve_role(user)
        load_manuscript_for_user(doi_suffix, session, user, role)

    zip_path = storage.output_zip(doi_suffix)
    if zip_path is None:
        raise HTTPException(404, detail="Output not yet available")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
