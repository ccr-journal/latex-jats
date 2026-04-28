"""Output zip download routes."""

import io
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
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


# Files the worker writes back into source_dir that aren't part of the
# author's upload. Excluded from the source archive so the zip stays a
# faithful copy of "what came in".
_WORKER_INJECTED_FILES = frozenset({"main.pdf"})


@router.get("/{doi_suffix}/download")
async def download_output(
    doi_suffix: str,
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    if token is not None:
        token_user = verify_token(token, doi_suffix)
        if token_user is None:
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


@router.get("/{doi_suffix}/download/source")
async def download_source(
    doi_suffix: str,
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Stream the author-supplied source plus a run manifest as a zip.

    Contents: a faithful copy of ``source_dir/`` (the upload as received,
    minus worker-injected artifacts like ``main.pdf``) and ``manifest.json``
    written by the worker at the end of the most recent pipeline run.
    Together these are enough to reproduce or re-run the conversion (e.g.
    against a different publisher or after a bug fix).
    """
    if token is not None:
        token_user = verify_token(token, doi_suffix)
        if token_user is None:
            raise HTTPException(401, detail="Invalid or expired presign token")
    else:
        user = _authenticate_bearer(authorization, session)
        role = await resolve_role(user)
        load_manuscript_for_user(doi_suffix, session, user, role)

    source_dir = storage.source_dir(doi_suffix)
    if source_dir.is_dir():
        files = sorted(
            p for p in source_dir.rglob("*")
            if p.is_file() and p.name not in _WORKER_INJECTED_FILES
        )
    else:
        files = []
    if not files:
        raise HTTPException(404, detail="No source files available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=str(path.relative_to(source_dir)))
        manifest = storage.manifest_path(doi_suffix)
        if manifest.is_file():
            zf.write(manifest, arcname="manifest.json")

    filename = f"{doi_suffix}_source.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
