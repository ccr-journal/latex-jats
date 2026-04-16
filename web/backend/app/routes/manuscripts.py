"""Manuscript CRUD routes."""

import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, select

from .. import ojs as ojs_client
from ..deps import (
    get_current_role,
    get_current_user,
    get_session,
    get_storage,
    load_manuscript_for_user,
    manuscript_to_read,
    require_editor,
)
from ..models import (
    CurrentUser,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptCreate,
    ManuscriptRead,
    ManuscriptStatus,
)
from ..storage import Storage

logger = logging.getLogger("latex_jats.web.manuscripts")

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.get("", response_model=list[ManuscriptRead])
def list_manuscripts(
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    if role == "editor":
        manuscripts = session.exec(
            select(Manuscript).order_by(Manuscript.created_at.desc())
        ).all()
    else:
        manuscripts = session.exec(
            select(Manuscript)
            .join(ManuscriptAuthor, ManuscriptAuthor.manuscript_id == Manuscript.doi_suffix)
            .where(ManuscriptAuthor.orcid == user.orcid)
            .order_by(Manuscript.created_at.desc())
        ).all()
    return [manuscript_to_read(ms, session) for ms in manuscripts]


@router.post("", response_model=ManuscriptRead, status_code=201)
def create_manuscript(
    body: ManuscriptCreate,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    existing = session.get(Manuscript, body.doi_suffix)
    if existing:
        raise HTTPException(409, detail=f"Manuscript '{body.doi_suffix}' already exists")
    ms = Manuscript(**body.model_dump())
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


class ManuscriptUpdate(SQLModel):
    fix_source: bool | None = None


@router.patch("/{doi_suffix}", response_model=ManuscriptRead)
def update_manuscript(
    doi_suffix: str,
    body: ManuscriptUpdate,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    if body.fix_source is not None:
        ms.fix_source = body.fix_source
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.post("/{doi_suffix}/approve", response_model=ManuscriptRead)
def approve_manuscript(
    doi_suffix: str,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if ms.status != ManuscriptStatus.ready:
        raise HTTPException(
            400, detail=f"Only manuscripts with status 'ready' can be approved (current: {ms.status.value})"
        )
    ms.status = ManuscriptStatus.approved
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.post("/{doi_suffix}/withdraw-approval", response_model=ManuscriptRead)
async def withdraw_approval(
    doi_suffix: str,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
):
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if ms.status != ManuscriptStatus.approved:
        raise HTTPException(
            400, detail=f"Only approved manuscripts can have approval withdrawn (current: {ms.status.value})"
        )
    if ms.ojs_submission_id:
        try:
            in_production = await ojs_client.is_submission_in_production(ms.ojs_submission_id)
        except ojs_client.OjsAdminTokenInvalid as exc:
            logger.error("OJS admin token invalid: %s", exc)
            raise HTTPException(502, detail="OJS admin token invalid")
        except ojs_client.OjsUnavailable as exc:
            logger.error("OJS unavailable: %s", exc)
            raise HTTPException(502, detail=f"OJS unavailable: {exc}")
        if in_production:
            raise HTTPException(
                409, detail="Cannot withdraw approval: the submission has already moved to production in OJS"
            )
    ms.status = ManuscriptStatus.ready
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return manuscript_to_read(ms, session)


@router.get("/{doi_suffix}", response_model=ManuscriptRead)
def get_manuscript(
    doi_suffix: str,
    user: CurrentUser = Depends(get_current_user),
    role: Literal["editor", "author"] = Depends(get_current_role),
    session: Session = Depends(get_session),
):
    ms = load_manuscript_for_user(doi_suffix, session, user, role)
    return manuscript_to_read(ms, session)


# ── OJS metadata re-import ────────────────────────────────────────────────────


@router.post("/{doi_suffix}/reimport-ojs", response_model=ManuscriptRead)
async def reimport_ojs_metadata(
    doi_suffix: str,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Re-fetch metadata from OJS and update the local manuscript record."""
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if not ms.ojs_submission_id:
        raise HTTPException(400, detail="Manuscript is not linked to an OJS submission")

    try:
        sub = await ojs_client.fetch_submission(ms.ojs_submission_id)
    except ojs_client.OjsAdminTokenInvalid as exc:
        logger.error("OJS admin token invalid: %s", exc)
        raise HTTPException(502, detail="OJS admin token invalid")
    except ojs_client.OjsUnavailable as exc:
        logger.error("OJS unavailable: %s", exc)
        raise HTTPException(502, detail=f"OJS unavailable: {exc}")

    if sub is None:
        raise HTTPException(404, detail="OJS submission not found")

    _apply_ojs_submission(ms, sub, doi_suffix, session)

    # Re-run check step if comparison data exists
    _rerun_check_step(doi_suffix, session, storage)

    return manuscript_to_read(ms, session)


def _apply_ojs_submission(ms, sub, doi_suffix, session):
    """Update a Manuscript and its authors from an OjsSubmission."""
    ms.title = sub.title or None
    ms.subtitle = sub.subtitle
    ms.abstract = sub.abstract
    ms.keywords = list(sub.keywords) if sub.keywords else None
    ms.doi = sub.doi
    ms.volume = sub.volume
    ms.issue_number = sub.issue_number
    ms.year = sub.year
    session.add(ms)

    # Replace authors
    existing = session.exec(
        select(ManuscriptAuthor).where(ManuscriptAuthor.manuscript_id == doi_suffix)
    ).all()
    for a in existing:
        session.delete(a)
    for a in sub.authors:
        session.add(ManuscriptAuthor(
            manuscript_id=doi_suffix, orcid=a.orcid, name=a.name, order=a.order,
        ))
    session.commit()
    session.refresh(ms)


# ── OJS metadata sync ────────────────────────────────────────────────────────

_UPDATABLE_FIELDS = {"title", "subtitle", "abstract", "keywords"}


class SyncOjsRequest(BaseModel):
    field: str


@router.post("/{doi_suffix}/sync-ojs")
async def sync_ojs_field(
    doi_suffix: str,
    body: SyncOjsRequest,
    _editor: str = Depends(require_editor),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Push a single metadata field from LaTeX/JATS output to OJS."""
    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")
    if not ms.ojs_submission_id:
        raise HTTPException(400, detail="Manuscript is not linked to an OJS submission")
    if body.field not in _UPDATABLE_FIELDS:
        raise HTTPException(
            400, detail=f"Field '{body.field}' is not updatable (allowed: {sorted(_UPDATABLE_FIELDS)})"
        )

    # Read the comparison file to get the LaTeX value
    comparison_path = storage.convert_output_dir(doi_suffix) / "metadata_comparison.json"
    if not comparison_path.is_file():
        raise HTTPException(404, detail="No metadata comparison data available")

    comparisons = json.loads(comparison_path.read_text())
    entry = next((c for c in comparisons if c["field"] == body.field), None)
    if entry is None:
        raise HTTPException(404, detail=f"Field '{body.field}' not found in comparison data")
    if entry["status"] != "mismatch":
        raise HTTPException(400, detail=f"Field '{body.field}' already matches")

    latex_value = entry["latex"]

    # Step 1: Push to OJS
    try:
        if body.field == "authors":
            await ojs_client.update_publication_authors(
                ms.ojs_submission_id, latex_value
            )
        else:
            await ojs_client.update_publication_field(
                ms.ojs_submission_id, body.field, latex_value
            )
    except ojs_client.OjsAdminTokenInvalid as exc:
        logger.error("OJS admin token invalid: %s", exc)
        raise HTTPException(502, detail="OJS admin token invalid")
    except ojs_client.OjsUnavailable as exc:
        logger.error("OJS unavailable: %s", exc)
        raise HTTPException(502, detail=f"OJS unavailable: {exc}")

    # Step 2: Re-import metadata from OJS to keep local DB in sync
    try:
        updated_sub = await ojs_client.fetch_submission(ms.ojs_submission_id)
    except (ojs_client.OjsAdminTokenInvalid, ojs_client.OjsUnavailable) as exc:
        logger.warning("Could not re-fetch submission after update: %s", exc)
        updated_sub = None

    if updated_sub is not None:
        _apply_ojs_submission(ms, updated_sub, doi_suffix, session)

    # Step 3: Re-run comparison and update the check pipeline step
    _rerun_check_step(doi_suffix, session, storage)

    # Return updated comparisons
    comparisons = json.loads(comparison_path.read_text()) if comparison_path.is_file() else []
    return comparisons


def _rerun_check_step(
    doi_suffix: str, session: Session, storage: Storage
) -> None:
    """Re-run metadata comparison and update the check pipeline step."""
    import logging as _logging

    from latex_jats.convert import compare_metadata
    from ..worker import classify_step_status

    convert_dir = storage.convert_output_dir(doi_suffix)
    xml_files = list(convert_dir.glob("*.xml"))
    if not xml_files:
        return
    output_xml = xml_files[0]

    ms = session.get(Manuscript, doi_suffix)
    if ms is None:
        return
    authors = session.exec(
        select(ManuscriptAuthor)
        .where(ManuscriptAuthor.manuscript_id == doi_suffix)
        .order_by(ManuscriptAuthor.order)
    ).all()

    # Capture log output from compare_metadata
    log_buffer: list[str] = []
    handler = _logging.Handler()
    handler.setFormatter(_logging.Formatter("%(levelname)s: %(message)s"))
    handler.emit = lambda record: log_buffer.append(handler.format(record))  # type: ignore[assignment]
    meta_logger = _logging.getLogger("latex_jats")
    meta_logger.addHandler(handler)
    try:
        compare_metadata(
            output_xml, ms, authors,
            output_json=convert_dir / "metadata_comparison.json",
        )
    finally:
        meta_logger.removeHandler(handler)

    # Update the check step in pipeline_steps
    log_text = "\n".join(log_buffer)
    status = classify_step_status(log_text)
    if ms.pipeline_steps:
        from datetime import datetime
        steps = [dict(s) for s in ms.pipeline_steps]
        for step in steps:
            if step["name"] == "check":
                step["status"] = status
                step["logs"] = [{"name": "pipeline", "content": log_text}] if log_text.strip() else []
                step["completed_at"] = datetime.utcnow().isoformat()
                break
        ms.pipeline_steps = steps
        session.add(ms)
        session.commit()
