# Website Design: LaTeX-JATS Web Service

## Overview

A web service where editors can create manuscripts linked to OJS submissions, share secure links with authors for uploading LaTeX/Quarto source files, and manage the conversion pipeline through to production-ready JATS XML.

## Workflow

1. **Editor** creates a new manuscript (optionally importing metadata from OJS)
2. Editor shares a **secure link** with the author
3. **Author** (or editor) uploads LaTeX/QMD source + resources (images, bibliography, etc.)
4. System runs the conversion pipeline (prepare, convert, package)
5. Author reviews **compilation/conversion warnings**, checks **PDF and HTML proofs**
6. Author uploads new versions until satisfied
7. **Editor** downloads the final zip for production (or pushes it back to OJS)

## Architecture

```
┌─────────────┐      ┌──────────────────────────────┐
│  Vite/React │─────▶│  FastAPI                     │
│  SPA        │◀─────│                              │
│             │ poll  │  /api/manuscripts             │
└─────────────┘      │  /api/manuscripts/:id/upload  │
                     │  /api/manuscripts/:id/status  │
                     │  /api/manuscripts/:id/download │
                     │  /api/ojs/import              │
                     │                              │
                     │  Background worker (in-proc) │
                     │  ┌─────────────────────────┐ │
                     │  │ prepare → convert → zip  │ │
                     │  └─────────────────────────┘ │
                     │                              │
                     │  SQLite    File storage      │
                     │  (metadata, (uploads/output) │
                     │   logs,                      │
                     │   tokens)                    │
                     └──────────────────────────────┘
```

## Repository structure: monorepo

The web service lives in the same repository as the `latex_jats` conversion pipeline. Reasons:

- **Co-deployed:** the Docker image needs both the web service and the pipeline with all its system dependencies (TeX Live, latexmlc, inkscape). They always ship together.
- **Pipeline is evolving:** active development on fixup functions and LaTeXML bindings. A separate PyPI package would add a publish-then-update cycle for every change.
- **Narrow audience:** this tool is specific to CCR/AUP, not a general-purpose library with external consumers.
- **CLI still works standalone:** `uv run latex-jats` doesn't require web dependencies. Separation is at the dependency level (optional `[web]` extras group in `pyproject.toml`), not the repo level.

## Technology choices

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Vite + React | Simple SPA, no SSR needed |
| Backend | FastAPI (Python) | Directly imports existing `latex_jats` pipeline; avoids shelling out |
| Database | SQLite (via SQLModel) | Zero infrastructure, sufficient for expected volume |
| File storage | Local filesystem | Abstracted behind a storage interface for future S3 migration |
| Job processing | In-process background tasks | Low concurrency expected; avoids Redis/Celery overhead |
| Deployment | Docker on VPS | Pipeline requires TeX Live, latexmlc, inkscape — too heavy for serverless |
| Migrations | Alembic | Standard SQLModel/SQLAlchemy migration tool |

## Authentication and access model

- **Editors** authenticate via OJS API credentials (or simple username/password as fallback)
- **Authors** receive a secure capability URL containing a signed token (JWT or random token) granting access to a single manuscript
- No author accounts needed — access is per-manuscript via the shared link

## OJS integration (optional)

The system can optionally connect to the OJS REST API (v3) for a journal:

- **Import metadata:** pull title, authors, DOI, volume/issue from an OJS submission ID
- **Authentication:** editor identity verified through OJS credentials
- **Delivery:** push the final zip back to OJS, closing the production loop

The OJS integration is optional — manuscripts can also be created and managed manually, which is useful for development, testing, and standalone use.

## Data model

### Manuscript

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| title | str | From OJS or manually entered |
| doi_suffix | str | e.g. `CCR2025.1.2.YAO` |
| ojs_submission_id | int? | Optional link to OJS |
| status | enum | `draft`, `processing`, `ready`, `published` |
| created_at | datetime | |
| updated_at | datetime | |

### Version

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| manuscript_id | UUID | Foreign key |
| version_number | int | Auto-incrementing per manuscript |
| uploaded_at | datetime | |
| uploaded_by | str | `editor` or `author` |

### ConversionJob

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| version_id | UUID | Foreign key |
| status | enum | `queued`, `running`, `completed`, `failed` |
| started_at | datetime? | |
| completed_at | datetime? | |
| log | text | Conversion log output (warnings, errors) |

### AccessToken

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| manuscript_id | UUID | Foreign key |
| token | str | Random token or JWT |
| role | enum | `editor`, `author` |
| created_at | datetime | |
| expires_at | datetime? | Optional expiry |

## File storage layout

```
storage/
  manuscripts/
    <manuscript-id>/
      versions/
        <version-number>/
          source/            # uploaded files (tex, bib, images, etc.)
          output/
            prepare/         # compilation logs, status.json
            convert/         # JATS XML, HTML, PDF, images, zip
```

## Frontend pages

- **Editor dashboard** — list of manuscripts with status indicators
- **Manuscript detail** — metadata, version history, current status, download link
- **Upload** — drag-and-drop zip or multi-file upload, with version note
- **Preview** — HTML proof (iframe), PDF link, conversion log with warnings/errors
- **Author view** — same as manuscript detail but scoped to one manuscript via token

## Progress feedback

Status polling (not websockets) — the frontend polls `/api/manuscripts/:id/status` while a job is running and displays a progress indicator. The backend updates job status as the pipeline progresses through stages (preparing, converting, packaging).

## Project structure

```
web/
  frontend/              # Vite + React SPA
    src/
      pages/
      components/
      api/               # typed API client
  backend/
    app/
      main.py            # FastAPI app, CORS, lifespan
      routes/            # manuscripts, upload, download, ojs
      models.py          # SQLModel table definitions
      worker.py          # background job runner
      storage.py         # file storage abstraction
      ojs.py             # OJS API client
    alembic/             # database migrations
src/                     # existing latex_jats package (unchanged)
Dockerfile
docker-compose.yml
```

The existing `src/latex_jats/` package stays unchanged. The backend imports and calls `convert()` directly.

## Implementation plan

1. **Backend skeleton** — FastAPI app with manuscript CRUD, file upload, SQLite models
2. **Pipeline integration** — background worker calls existing `convert()`, stores logs in DB
3. **Frontend** — upload flow, status polling, proof preview (HTML iframe + PDF link)
4. **Secure author links** — token-based access to individual manuscripts
5. **OJS integration** — import metadata, push zip back
6. **Docker packaging** — Dockerfile with TeX Live, latexmlc, inkscape, app
