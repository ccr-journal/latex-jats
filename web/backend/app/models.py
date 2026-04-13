"""SQLModel table definitions, enums, and Pydantic response schemas."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


# ── Enums ─────────────────────────────────────────────────────────────────────


class ManuscriptStatus(str, Enum):
    draft = "draft"
    processing = "processing"
    ready = "ready"
    published = "published"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


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


class ConversionJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    manuscript_id: str = Field(foreign_key="manuscript.doi_suffix", index=True)
    status: JobStatus = JobStatus.queued
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    log: str = ""  # accumulates pipeline output


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


class JobRead(SQLModel):
    id: str
    manuscript_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    log: str


class StatusResponse(SQLModel):
    manuscript_status: ManuscriptStatus
    job: Optional[JobRead]
