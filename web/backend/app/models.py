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
    use_canonical_class_file: bool = True
    uploaded_at: Optional[datetime] = None
    uploaded_by: Optional[str] = None  # "editor" | "author" | "upstream"
    job_log: str = ""
    job_started_at: Optional[datetime] = None
    job_completed_at: Optional[datetime] = None
    pipeline_steps: Optional[list] = Field(default=None, sa_column=Column(JSON, nullable=True))
    # Upstream source linkage (Issue #7). file:// URLs point at source_dir for
    # uploads; https:// / git@ URLs are external and syncable.
    upstream_url: Optional[str] = None
    upstream_token_encrypted: Optional[bytes] = None
    upstream_ref: Optional[str] = None       # branch/tag/commit; None = remote HEAD
    upstream_subpath: Optional[str] = None   # subdir inside the repo
    main_file: Optional[str] = None          # entrypoint; None = auto-detect
    last_synced_at: Optional[datetime] = None
    last_synced_sha: Optional[str] = None
    # Approval audit (Issue #9). Set when an author confirms camera-ready;
    # cleared on withdraw-approval.
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    # Per-conversion email notification opt-in (Issue #37). Set by POST
    # /process when the user opts in; cleared by the worker after a
    # successful send. Not surfaced on ManuscriptRead — internal only.
    notify_email: Optional[str] = None


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


class DiagnosisChat(SQLModel, table=True):
    """One Claude diagnosis chat per manuscript (Issue #36).

    Stores the full transcript so editors can audit what Claude told the
    author. ``messages`` is a JSON list of dicts with shape
    ``{role, content, created_at, input_tokens?, output_tokens?, cache_read_tokens?}``.
    Usage counters are populated on assistant turns for cost monitoring;
    they're absent on user turns.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    manuscript_id: str = Field(
        foreign_key="manuscript.doi_suffix", unique=True, index=True
    )
    messages: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SiteConfig(SQLModel, table=True):
    """Singleton row (id=1) holding journal-identity config that used to live in
    convert.py constants and OJS_* env vars. Edited via /api/site-config; seeded
    with CCR defaults by the 0011 alembic migration so existing deployments are
    unchanged after upgrade.
    """
    id: int = Field(default=1, primary_key=True)
    # JATS <journal-meta>
    journal_id: str
    journal_title: str
    issn_epub: str = ""
    issn_ppub: str = ""
    publisher_name: str
    publisher_loc: str
    # JATS <permissions>
    copyright_holder: str
    copyright_statement: str
    license_type: str = "open-access"
    license_url: str
    license_text: str
    # DOI
    doi_prefix: str
    # Branding (Issue #32, action point 6). Defaults live in the alembic
    # migration (server_default for backfill) and in DEFAULT_SITE_CONFIG (the
    # CLI fallback). They're intentionally absent here: nothing in the running
    # code constructs SiteConfig(...) — route handlers update the existing
    # row, tests seed every field, and migrations use raw SQL.
    site_name: str
    site_description: str
    header_branding: str
    # Canonical class-file & Quarto-extension sources (Issue #32). Both
    # optional; empty disables the "use latest class file" feature for this
    # journal. The URL is fetched on app start and re-fetched when changed
    # via PUT /api/site-config; see canonical_extension.fetch_canonical_bundle.
    class_file_url: str
    quarto_extension_repo: str
    # Null until the editor confirms via the form; drives the first-login banner.
    configured_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    smtp_enabled: bool = False
    claude_api_enabled: bool = False


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
    use_canonical_class_file: bool = True
    created_at: datetime
    updated_at: datetime
    uploaded_at: Optional[datetime]
    uploaded_by: Optional[str]
    upload_file_count: Optional[int] = None  # computed, not stored
    job_log: str
    job_started_at: Optional[datetime]
    job_completed_at: Optional[datetime]
    pipeline_steps: Optional[list[PipelineStepRead]] = None
    # Upstream source (Issue #7). Token field is intentionally not exposed;
    # the client only sees whether one is stored.
    upstream_url: Optional[str] = None
    upstream_ref: Optional[str] = None
    upstream_subpath: Optional[str] = None
    upstream_has_token: bool = False
    main_file: Optional[str] = None
    # Computed (not stored). True when the source is a Quarto project — set
    # by manuscript_to_read using the same heuristic as the worker. Drives
    # source-aware UI bits like the "Use latest …" toggle label.
    is_quarto: bool = False
    last_synced_at: Optional[datetime] = None
    last_synced_sha: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None


class SiteConfigRead(SQLModel):
    journal_id: str
    journal_title: str
    issn_epub: str
    issn_ppub: str
    publisher_name: str
    publisher_loc: str
    copyright_holder: str
    copyright_statement: str
    license_type: str
    license_url: str
    license_text: str
    doi_prefix: str
    site_name: str
    site_description: str
    header_branding: str
    class_file_url: str
    quarto_extension_repo: str
    configured_at: Optional[datetime] = None
    updated_at: datetime


class DiagnosisMessageRead(SQLModel):
    role: str  # "user" | "assistant"
    content: str
    created_at: str  # iso8601
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None


class DiagnosisChatRead(SQLModel):
    id: str
    manuscript_id: str
    messages: list[DiagnosisMessageRead] = []
    created_at: datetime
    updated_at: datetime
    # True when the manuscript has been re-converted since this chat was
    # created. The chat's first turn captures source + logs at that moment;
    # if the pipeline has run again the chat is reasoning about an old
    # state, so the UI shows a warning and disables follow-ups (the user
    # can still read the prior advice; clearing starts a fresh chat).
    is_stale: bool = False


class DiagnosisMessageCreate(SQLModel):
    content: str = ""
    # Only consulted on the first turn — controls whether the failure
    # context attached as the seed message includes the source-file
    # bundle, or just the pipeline logs. Ignored on follow-ups (the
    # source is already in the conversation history).
    include_source: bool = True


class SiteConfigUpdate(SQLModel):
    journal_id: Optional[str] = None
    journal_title: Optional[str] = None
    issn_epub: Optional[str] = None
    issn_ppub: Optional[str] = None
    publisher_name: Optional[str] = None
    publisher_loc: Optional[str] = None
    copyright_holder: Optional[str] = None
    copyright_statement: Optional[str] = None
    license_type: Optional[str] = None
    license_url: Optional[str] = None
    license_text: Optional[str] = None
    doi_prefix: Optional[str] = None
    site_name: Optional[str] = None
    site_description: Optional[str] = None
    header_branding: Optional[str] = None
    class_file_url: Optional[str] = None
    quarto_extension_repo: Optional[str] = None
