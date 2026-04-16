"""SQLModel table definitions, enums, and Pydantic response schemas."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


# ── Enums ─────────────────────────────────────────────────────────────────────


class ManuscriptStatus(str, Enum):
    draft = "draft"
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    approved = "approved"
    failed = "failed"
    published = "published"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    ok = "ok"
    warnings = "warnings"
    errors = "errors"
    failed = "failed"
    skipped = "skipped"


PIPELINE_STEPS = ["prepare", "compile", "convert", "check", "validate"]


# ── Tables ────────────────────────────────────────────────────────────────────


class Manuscript(SQLModel, table=True):
    doi_suffix: str = Field(primary_key=True)
    ojs_submission_id: Optional[int] = None
    status: ManuscriptStatus = ManuscriptStatus.draft
    # OJS-imported metadata (populated on /api/ojs/submissions/{id}/import)
    title: Optional[str] = None
    subtitle: Optional[str] = None
    abstract: Optional[str] = None  # HTML
    keywords: Optional[list] = Field(default=None, sa_column=Column(JSON, nullable=True))
    doi: Optional[str] = None
    volume: Optional[str] = None
    issue_number: Optional[str] = None
    year: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    fix_source: bool = False
    uploaded_at: Optional[datetime] = None
    uploaded_by: Optional[str] = None  # "editor" | "author"
    job_log: str = ""
    job_started_at: Optional[datetime] = None
    job_completed_at: Optional[datetime] = None
    pipeline_steps: Optional[list] = Field(default=None, sa_column=Column(JSON, nullable=True))


class ManuscriptAuthor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: str = Field(foreign_key="manuscript.doi_suffix", index=True)
    orcid: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = None
    order: int = 0


class AccessToken(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    token: str = Field(index=True, unique=True)
    orcid: str = Field(index=True)
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class LoginState(SQLModel, table=True):
    state: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Request / response schemas ────────────────────────────────────────────────


class ManuscriptCreate(SQLModel):
    doi_suffix: str
    ojs_submission_id: Optional[int] = None


class CurrentUser(SQLModel):
    orcid: str
    name: Optional[str] = None


class CurrentUserWithRole(SQLModel):
    orcid: str
    name: Optional[str] = None
    role: str  # "editor" | "author"


class AuthorRead(SQLModel):
    orcid: Optional[str] = None
    name: Optional[str] = None
    order: int = 0


class StepLogEntry(SQLModel):
    name: str
    content: str


class PipelineStepRead(SQLModel):
    name: str
    status: str
    logs: list[StepLogEntry] = []
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ManuscriptRead(SQLModel):
    doi_suffix: str
    ojs_submission_id: Optional[int]
    status: ManuscriptStatus
    title: Optional[str] = None
    subtitle: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[list[str]] = None
    doi: Optional[str] = None
    volume: Optional[str] = None
    issue_number: Optional[str] = None
    year: Optional[int] = None
    authors: list[AuthorRead] = []
    fix_source: bool = False
    created_at: datetime
    updated_at: datetime
    uploaded_at: Optional[datetime]
    uploaded_by: Optional[str]
    upload_file_count: Optional[int] = None  # computed, not stored
    job_log: str
    job_started_at: Optional[datetime]
    job_completed_at: Optional[datetime]
    pipeline_steps: Optional[list[PipelineStepRead]] = None
