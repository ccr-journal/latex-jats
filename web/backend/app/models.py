"""SQLModel table definitions, enums, and Pydantic response schemas."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


# ── Enums ─────────────────────────────────────────────────────────────────────


class ManuscriptStatus(str, Enum):
    draft = "draft"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    published = "published"


class TokenRole(str, Enum):
    editor = "editor"
    author = "author"


# ── Tables ────────────────────────────────────────────────────────────────────


class Manuscript(SQLModel, table=True):
    doi_suffix: str = Field(primary_key=True)
    title: str
    ojs_submission_id: Optional[int] = None
    status: ManuscriptStatus = ManuscriptStatus.draft
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_at: Optional[datetime] = None
    uploaded_by: Optional[str] = None  # "editor" | "author"
    job_log: str = ""
    job_started_at: Optional[datetime] = None
    job_completed_at: Optional[datetime] = None


class AccessToken(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    manuscript_id: str = Field(foreign_key="manuscript.doi_suffix", index=True)
    token: str = Field(index=True)
    role: TokenRole
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


# ── Request / response schemas ────────────────────────────────────────────────


class ManuscriptCreate(SQLModel):
    title: str
    doi_suffix: str
    ojs_submission_id: Optional[int] = None


class ManuscriptRead(SQLModel):
    doi_suffix: str
    title: str
    ojs_submission_id: Optional[int]
    status: ManuscriptStatus
    created_at: datetime
    updated_at: datetime
    uploaded_at: Optional[datetime]
    uploaded_by: Optional[str]
    job_log: str
    job_started_at: Optional[datetime]
    job_completed_at: Optional[datetime]
