"""Editor password login / logout / current-user routes."""

from __future__ import annotations

import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import get_config
from ..deps import get_current_role, get_current_user, get_session
from ..models import AccessToken, CurrentUser, CurrentUserWithRole

logger = logging.getLogger("jatsmith.web.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: CurrentUserWithRole


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    cfg = get_config()
    expected = cfg.editor_credentials.get(body.username)
    # Always run compare_digest against *something* to keep the timing the
    # same whether or not the username exists.
    probe = expected if expected is not None else ""
    ok = hmac.compare_digest(probe, body.password) and expected is not None
    if not ok:
        raise HTTPException(401, detail="Invalid username or password")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=cfg.session_token_ttl_days)
    session.add(
        AccessToken(
            token=token,
            username=body.username,
            name=None,
            expires_at=expires_at,
        )
    )
    session.commit()
    return LoginResponse(
        token=token,
        user=CurrentUserWithRole(username=body.username, name=None, role="editor"),
    )


@router.post("/logout", status_code=204)
def logout(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="Missing or malformed Authorization header")
    token = authorization.split(None, 1)[1].strip()
    row = session.exec(select(AccessToken).where(AccessToken.token == token)).first()
    if row is not None:
        session.delete(row)
        session.commit()


@router.get("/me", response_model=CurrentUserWithRole)
async def me(
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
):
    return CurrentUserWithRole(
        username=user.username,
        name=user.name,
        role=role,
        manuscript_token_scope=user.manuscript_token_scope,
    )
