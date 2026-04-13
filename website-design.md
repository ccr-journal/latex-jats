# Website Design: LaTeX-JATS Web Service

## Overview

A web service where editors can create manuscripts linked to OJS submissions, share secure links with authors for uploading LaTeX/Quarto source files, and manage the conversion pipeline through to production-ready JATS XML.

## Workflow

1. **Editor** creates a new manuscript (optionally importing metadata from OJS)
2. Editor shares a **secure link** with the author
3. **Author** (or editor) uploads LaTeX/QMD source + resources (images, bibliography, etc.)
4. System runs the conversion pipeline (prepare, convert, package)
5. Author reviews **compilation/conversion warnings**, checks **PDF and HTML proofs**
6. Author re-uploads if changes are needed
7. **Editor** downloads the final zip for production (or pushes it back to OJS)

## Architecture

```
┌─────────────┐      ┌───────────────────────────────┐
│  Vite/React │─────▶│  FastAPI                      │
│  SPA        │◀─────│                               │
│             │ poll │  /api/manuscripts             │
└─────────────┘      │  /api/manuscripts/:id/upload  │
                     │  /api/manuscripts/:id/status  │
                     │  /api/manuscripts/:id/download│
                     │  /api/manuscripts/:id/output/ │
                     │  /api/ojs/import              │
                     │                               │
                     │  Background worker (in-proc)  │
                     │  ┌─────────────────────────┐  │
                     │  │ prepare → convert → zip │  │
                     │  └─────────────────────────┘  │
                     │                               │
                     │  SQLite    File storage       │
                     │  (metadata, (uploads/output)  │
                     │   logs,                       │
                     │   tokens)                     │
                     └───────────────────────────────┘
```

## Repository structure: monorepo

The web service lives in the same repository as the `latex_jats` conversion pipeline. Reasons:

- **Co-deployed:** the Docker image needs both the web service and the pipeline with all its system dependencies (TeX Live, latexmlc, inkscape). They always ship together.
- **Pipeline is evolving:** active development on fixup functions and LaTeXML bindings. A separate PyPI package would add a publish-then-update cycle for every change.
- **Narrow audience:** this tool is specific to CCR/AUP, not a general-purpose library with external consumers.
- **CLI still works standalone:** `uv run latex-jats` doesn't require web dependencies. Separation is at the dependency level (optional `[web]` extras group in `pyproject.toml`), not the repo level.

## Technology choices

| Layer          | Choice                      | Rationale                                                                 |
| -------------- | --------------------------- | ------------------------------------------------------------------------- |
| Frontend       | Vite + React                | Simple SPA, no SSR needed                                                 |
| Backend        | FastAPI (Python)            | Directly imports existing `latex_jats` pipeline; avoids shelling out      |
| Database       | SQLite (via SQLModel)       | Zero infrastructure, sufficient for expected volume                       |
| File storage   | Local filesystem            | Abstracted behind a storage interface for future S3 migration             |
| Job processing | In-process background tasks | Low concurrency expected; avoids Redis/Celery overhead                    |
| Deployment     | Docker on VPS               | Pipeline requires TeX Live, latexmlc, inkscape — too heavy for serverless |
| Migrations     | Alembic                     | Standard SQLModel/SQLAlchemy migration tool                               |

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

| Field             | Type      | Notes                                                        |
| ----------------- | --------- | ------------------------------------------------------------ |
| doi_suffix        | str       | Primary key, e.g. `CCR2025.1.2.YAO`                         |
| title             | str       | From OJS or manually entered                                 |
| ojs_submission_id | int?      | Optional link to OJS                                         |
| status            | enum      | `draft`, `queued`, `processing`, `ready`, `failed`, `published` |
| created_at        | datetime  |                                                              |
| updated_at        | datetime  |                                                              |
| uploaded_at       | datetime? | Set when source is uploaded                                  |
| uploaded_by       | str?      | `editor` or `author`                                         |
| job_log           | text      | Conversion log output (warnings, errors)                     |
| job_started_at    | datetime? | When pipeline started                                        |
| job_completed_at  | datetime? | When pipeline finished                                       |

No separate ConversionJob table — conversion state is on the Manuscript directly (see step 2 design decisions below).

### AccessToken

| Field         | Type      | Notes                      |
| ------------- | --------- | -------------------------- |
| id            | UUID      | Primary key                |
| manuscript_id | str       | Foreign key → Manuscript.doi_suffix |
| token         | str       | Random token or JWT        |
| role          | enum      | `editor`, `author`         |
| created_at    | datetime  |                            |
| expires_at    | datetime? | Optional expiry            |

## File storage layout

```
storage/
  manuscripts/
    <doi_suffix>/
      source/            # uploaded files (tex, bib, images, etc.)
      output/
        prepare/         # compilation logs, status.json
        convert/         # JATS XML, HTML, PDF, images, zip
```

## Frontend pages

- **Editor dashboard** — list of manuscripts with status indicators
- **Manuscript detail** — metadata, current status, download link
- **Upload** — drag-and-drop zip or multi-file upload
- **Preview** — HTML proof (iframe), PDF link, conversion log with warnings/errors
- **Author view** — same as manuscript detail but scoped to one manuscript via token

## Progress feedback

Status polling (not websockets) — the frontend polls `/api/manuscripts/:id/status` while a job is running and displays a progress indicator. The backend updates job status as the pipeline progresses through stages (preparing, converting, packaging).

## Project structure

```
web/
  frontend/              # Vite + React + TypeScript + shadcn/ui SPA
    src/
      api/               # typed API client (client.ts, types.ts)
      pages/             # DashboardPage, ManuscriptPage, PreviewPage
      components/        # Layout, StatusBadge, UploadZone, LogViewer, CreateManuscriptDialog
      components/ui/     # shadcn/ui primitives (badge, button, card, dialog, input, label, table)
  backend/
    app/
      main.py            # FastAPI app, CORS, lifespan, static file serving
      deps.py            # get_session / get_storage dependency callables
      models.py          # SQLModel table definitions
      storage.py         # file storage abstraction
      worker.py          # background job runner
      ojs.py             # OJS API client (step 5, planned)
      routes/
        manuscripts.py   # GET+POST /api/manuscripts, GET /api/manuscripts/:id
        upload.py        # POST /api/manuscripts/:id/upload
        status.py        # GET /api/manuscripts/:id/status
        download.py      # GET /api/manuscripts/:id/download
        output.py        # GET /api/manuscripts/:id/output/{path} (serves HTML/PDF/images)
    alembic/             # database migrations
src/                     # existing latex_jats package (unchanged)
Dockerfile               # (step 6, planned)
docker-compose.yml       # (step 6, planned)
```

The existing `src/latex_jats/` package stays unchanged. The backend imports and calls `convert()` directly. In production, FastAPI serves the built frontend SPA from `web/frontend/dist/`.

## Implementation plan

1. **Backend skeleton** — FastAPI app with manuscript CRUD, file upload, SQLite models [Done]
2. **Pipeline integration** — background worker calls existing `convert()`, stores logs in DB [Done]
3. **Frontend** — Vite/React/shadcn/ui SPA with upload flow, status polling, HTML/PDF proof preview [Done]
4. **Secure author links** — token-based access to individual manuscripts
5. **OJS integration** — import metadata, push zip back
6. **Docker packaging** — Dockerfile with TeX Live, latexmlc, inkscape, app

## Step 2 design decisions

- **No separate `ConversionJob` table** — conversion state collapses into `Manuscript` directly (1:1; no job history needed).
- **Single status enum** on `Manuscript` covering the full lifecycle:
  `draft` → `queued` → `processing` → `ready` / `failed` → `published`
- **Job detail fields** added to `Manuscript`: `job_log` (text), `job_started_at`, `job_completed_at`.
- **`ManuscriptRead`** response schema includes the three job fields; `StatusResponse` is removed — `/status` returns `ManuscriptRead` directly.
- **Background tasks** via FastAPI `BackgroundTasks` (in-process; no Redis/Celery).
- **Log capture** via a custom `logging.Handler` attached to `logging.getLogger("latex_jats")`, flushed to `job_log` after each pipeline step (prepare → convert → zip) so the polling endpoint returns partial progress.
- **Worker** lives in `web/backend/app/worker.py`; called from the upload route after commit.
- **No Alembic migration** needed — DB is gitignored and auto-created on startup.
