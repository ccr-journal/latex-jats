"""ORCID OAuth login / logout / current-user routes."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from typing import Literal

from .. import orcid as orcid_client
from .. import ojs as ojs_client
from ..config import get_config
from ..deps import get_current_role, get_current_user, get_session
from ..models import AccessToken, CurrentUser, CurrentUserWithRole, LoginState

logger = logging.getLogger("latex_jats.web.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_STATE_TTL = timedelta(minutes=10)


def _prune_states(session: Session) -> None:
    cutoff = datetime.utcnow() - _STATE_TTL
    for stale in session.exec(select(LoginState).where(LoginState.created_at < cutoff)).all():
        session.delete(stale)


@router.get("/orcid/login")
def orcid_login(session: Session = Depends(get_session)):
    _prune_states(session)
    state = secrets.token_urlsafe(24)
    session.add(LoginState(state=state))
    session.commit()
    url = orcid_client.build_authorize_url(state)
    return RedirectResponse(url, status_code=302)


@router.get("/orcid/callback")
async def orcid_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
):
    cfg = get_config()

    state_row = session.get(LoginState, state)
    if state_row is None:
        raise HTTPException(400, detail="Invalid or expired login state")
    if datetime.utcnow() - state_row.created_at > _STATE_TTL:
        session.delete(state_row)
        session.commit()
        raise HTTPException(400, detail="Login state expired")
    session.delete(state_row)
    session.commit()

    try:
        identity = await orcid_client.exchange_code(code)
    except orcid_client.OrcidAuthError as exc:
        logger.warning("ORCID rejected code: %s", exc)
        raise HTTPException(401, detail="ORCID authentication failed")
    except orcid_client.OrcidUnavailable as exc:
        logger.error("ORCID unavailable: %s", exc)
        raise HTTPException(502, detail="ORCID service unavailable")

    # Warm the editor cache so the first role lookup after login is cheap.
    # Failures here are non-fatal: any ORCID user is allowed a session;
    # editor-gated endpoints will re-check and report cleanly if OJS is down.
    try:
        await ojs_client.fetch_editor_orcids()
    except (ojs_client.OjsAdminTokenInvalid, ojs_client.OjsUnavailable) as exc:
        logger.warning("OJS editor lookup failed during login: %s", exc)

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=cfg.session_token_ttl_days)
    session.add(
        AccessToken(
            token=token,
            orcid=identity.orcid,
            name=identity.name,
            expires_at=expires_at,
        )
    )
    session.commit()
    return RedirectResponse(
        f"{cfg.frontend_url}/auth/complete#token={token}",
        status_code=302,
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
        orcid=user.orcid,
        name=user.name,
        role=role,
        manuscript_token_scope=user.manuscript_token_scope,
    )
