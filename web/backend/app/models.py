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
    archived = "archived"


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
    date_received: Optional[str] = None    # YYYY-MM-DD; from OJS dateSubmitted
    date_accepted: Optional[str] = None    # YYYY-MM-DD; from OJS accept decision
    date_published: Optional[str] = None   # YYYY-MM-DD; from OJS datePublished
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    fix_source: bool = True
    use_canonical_ccr_cls: bool = True
    uploaded_at: Optional[datetime] = None
    uploaded_by: Optional[str] = None  # "editor" | "author"
    job_log: str = ""
    job_started_at: Optional[datetime] = None
    job_completed_at: Optional[datetime] = None
    pipeline_steps: Optional[list] = Field(default=None, sa_column=Column(JSON, nullable=True))


class ManuscriptAuthor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: str = Field(foreign_key="manuscript.doi_suffix", index=True)
    name: Optional[str] = None
    email: Optional[str] = None
    order: int = 0
    primary_contact: bool = Field(default=False)


class AccessToken(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    token: str = Field(index=True, unique=True)
    username: str = Field(index=True)
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class ManuscriptToken(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    manuscript_id: str = Field(foreign_key="manuscript.doi_suffix", unique=True, index=True)
    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Request / response schemas ────────────────────────────────────────────────


class ManuscriptCreate(SQLModel):
    doi_suffix: str
    ojs_submission_id: Optional[int] = None


class CurrentUser(SQLModel):
    username: Optional[str] = None
    name: Optional[str] = None
    manuscript_token_scope: Optional[str] = None  # doi_suffix if token-based


class CurrentUserWithRole(SQLModel):
    username: Optional[str] = None
    name: Optional[str] = None
    role: str  # "editor" | "author"
    manuscript_token_scope: Optional[str] = None


class AuthorRead(SQLModel):
    name: Optional[str] = None
    email: Optional[str] = None
    order: int = 0
    primary_contact: bool = False


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
    date_received: Optional[str] = None
    date_accepted: Optional[str] = None
    date_published: Optional[str] = None
    authors: list[AuthorRead] = []
    fix_source: bool = True
    use_canonical_ccr_cls: bool = True
    created_at: datetime
    updated_at: datetime
    uploaded_at: Optional[datetime]
    uploaded_by: Optional[str]
    upload_file_count: Optional[int] = None  # computed, not stored
    job_log: str
    job_started_at: Optional[datetime]
    job_completed_at: Optional[datetime]
    pipeline_steps: Optional[list[PipelineStepRead]] = None
