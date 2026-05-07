"""Claude diagnosis chat routes (Issue #36)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlmodel import Session, select

from .. import diagnosis
from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    get_storage,
    load_manuscript_for_user,
)
from ..models import (
    CurrentUser,
    DiagnosisChat,
    DiagnosisChatRead,
    DiagnosisMessageCreate,
    DiagnosisMessageRead,
)
from ..storage import Storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manuscripts", tags=["diagnosis"])

# Per the issue's guardrail: "Rate-limit per manuscript (e.g. max 5
# diagnoses/day)". Counted on user-role messages so an editor reset
# doesn't reopen the budget for the author.
RATE_LIMIT_PER_DAY = 5


def _to_read(chat: DiagnosisChat) -> DiagnosisChatRead:
    return DiagnosisChatRead(
        id=chat.id,
        manuscript_id=chat.manuscript_id,
        messages=[DiagnosisMessageRead(**m) for m in (chat.messages or [])],
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


def _user_messages_in_last_day(chat: DiagnosisChat) -> int:
    cutoff = datetime.utcnow() - timedelta(days=1)
    count = 0
    for m in chat.messages or []:
        if m.get("role") != "user":
            continue
        try:
            ts = datetime.fromisoformat(m.get("created_at", ""))
        except ValueError:
            continue
        if ts >= cutoff:
            count += 1
    return count


@router.get("/{doi_suffix}/diagnosis", response_model=DiagnosisChatRead | None)
def get_diagnosis(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    load_manuscript_for_user(doi_suffix, session, user, role)
    chat = session.exec(
        select(DiagnosisChat).where(DiagnosisChat.manuscript_id == doi_suffix)
    ).first()
    return _to_read(chat) if chat is not None else None


@router.post("/{doi_suffix}/diagnosis/messages", response_model=DiagnosisChatRead)
def post_diagnosis_message(
    doi_suffix: str,
    body: DiagnosisMessageCreate,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    if not diagnosis.is_enabled():
        raise HTTPException(
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Claude API is not configured (ANTHROPIC_API_KEY not set)",
        )
    ms = load_manuscript_for_user(doi_suffix, session, user, role)

    chat = session.exec(
        select(DiagnosisChat).where(DiagnosisChat.manuscript_id == doi_suffix)
    ).first()
    if chat is None:
        chat = DiagnosisChat(manuscript_id=doi_suffix, messages=[])
        session.add(chat)

    if _user_messages_in_last_day(chat) >= RATE_LIMIT_PER_DAY:
        raise HTTPException(
            http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limit of {RATE_LIMIT_PER_DAY} diagnoses per day reached",
        )

    # First turn seeds the failure context. If the user's content is empty
    # (the "Diagnose this conversion" button), the context blob is the
    # entire user message; otherwise we prepend it to their question.
    is_first_turn = not chat.messages
    user_text = body.content.strip()
    if is_first_turn:
        context = diagnosis.build_failure_context(
            ms, storage, include_source=body.include_source
        )
        if user_text:
            user_text = f"{context}\n\n# Author's question\n\n{user_text}"
        else:
            user_text = context

    if not user_text:
        raise HTTPException(400, detail="Empty message")

    now = datetime.utcnow()
    user_turn = {
        "role": "user",
        "content": user_text,
        "created_at": now.isoformat(),
    }
    new_messages = [*chat.messages, user_turn]

    # Build wire-format history (role/content only) for Claude.
    wire = [{"role": m["role"], "content": m["content"]} for m in new_messages]

    try:
        assistant = diagnosis.call_claude(wire)
    except Exception as e:
        logger.exception("Claude diagnosis call failed for %s", doi_suffix)
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Claude API error: {e}",
        )

    assistant_turn = {
        "role": "assistant",
        "content": assistant.content,
        "created_at": datetime.utcnow().isoformat(),
        "input_tokens": assistant.input_tokens,
        "output_tokens": assistant.output_tokens,
        "cache_read_tokens": assistant.cache_read_tokens,
    }
    chat.messages = [*new_messages, assistant_turn]
    chat.updated_at = datetime.utcnow()
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return _to_read(chat)


@router.delete("/{doi_suffix}/diagnosis", status_code=http_status.HTTP_204_NO_CONTENT)
def reset_diagnosis(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    load_manuscript_for_user(doi_suffix, session, user, role)
    chat = session.exec(
        select(DiagnosisChat).where(DiagnosisChat.manuscript_id == doi_suffix)
    ).first()
    if chat is not None:
        session.delete(chat)
        session.commit()
    return None
