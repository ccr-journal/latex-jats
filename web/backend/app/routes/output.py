"""Serve individual files from conversion output (HTML proof, CSS, images).

Also provides the ``/presign`` endpoint that generates short-lived tokens so
the browser can open output files (PDF, HTML preview) in new tabs or iframes
without needing an ``Authorization`` header.
"""

import mimetypes
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..deps import (
    _authenticate_bearer,
    get_current_role,
    get_current_user,
    get_session,
    get_storage,
    load_manuscript_for_user,
    resolve_role,
)
from ..models import CurrentUser
from ..presign import TOKEN_TTL_SECONDS, create_token, verify_token
from ..storage import Storage

router = APIRouter(prefix="/api/manuscripts", tags=["output"])

_COOKIE_NAME = "presign_token"


@router.get("/{doi_suffix}/presign")
async def presign(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    """Return a short-lived token for unauthenticated access to output files."""
    load_manuscript_for_user(doi_suffix, session, user, role)
    return {"token": create_token(doi_suffix, user.orcid)}


@router.get("/{doi_suffix}/output/{path:path}")
async def get_output_file(
    doi_suffix: str,
    path: str,
    request: Request,
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    # Resolve the presign token from query param or cookie
    effective_token = token or request.cookies.get(_COOKIE_NAME)

    if effective_token is not None:
        orcid = verify_token(effective_token, doi_suffix)
        if orcid is None:
            raise HTTPException(401, detail="Invalid or expired presign token")
    else:
        # Standard Bearer auth
        user = _authenticate_bearer(authorization, session)
        role = await resolve_role(user)
        load_manuscript_for_user(doi_suffix, session, user, role)

    output_dir = storage.convert_output_dir(doi_suffix)
    file_path = (output_dir / path).resolve()

    if not file_path.is_relative_to(output_dir.resolve()):
        raise HTTPException(404, detail="File not found")

    if not file_path.is_file():
        raise HTTPException(404, detail="File not found")

    media_type, _ = mimetypes.guess_type(file_path.name)
    response = FileResponse(file_path, media_type=media_type)

    # When the token came via query param, set a cookie so that sub-resources
    # loaded by the HTML page (CSS, images) are also authenticated.
    if token is not None and effective_token == token:
        response.set_cookie(
            _COOKIE_NAME,
            token,
            max_age=TOKEN_TTL_SECONDS,
            httponly=True,
            samesite="strict",
            path=f"/api/manuscripts/{doi_suffix}/output/",
        )

    return response
