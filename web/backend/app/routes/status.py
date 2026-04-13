"""Conversion status polling route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import get_session
from ..models import ConversionJob, JobRead, Manuscript, StatusResponse

router = APIRouter(prefix="/api/manuscripts", tags=["status"])

LOG_TAIL_CHARS = 2000


@router.get("/{doi_suffix}/status", response_model=StatusResponse)
def get_status(doi_suffix: str, session: Session = Depends(get_session)):
    ms = session.get(Manuscript, doi_suffix)
    if not ms:
        raise HTTPException(404, detail=f"Manuscript '{doi_suffix}' not found")

    job = session.exec(
        select(ConversionJob)
        .where(ConversionJob.manuscript_id == doi_suffix)
        .order_by(ConversionJob.created_at.desc())
    ).first()

    job_read = None
    if job:
        job_read = JobRead(
            id=job.id,
            manuscript_id=job.manuscript_id,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            log=job.log[-LOG_TAIL_CHARS:],
        )

    return StatusResponse(manuscript_status=ms.status, job=job_read)
