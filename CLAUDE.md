# CLAUDE.md

## Project overview

This tool converts CCR (Computational Communication Research) journal articles from LaTeX to JATS XML for submission to the AUP Online publishing platform. It uses LaTeXML with custom bindings and a Python post-processing pipeline, and can optionally produce an HTML proof preview.

A web service is built on top of this pipeline, where editors and authors can upload LaTeX source and check the conversion status. The FastAPI backend is in `web/backend/` (with pipeline integration), and a React frontend is in `web/frontend/`.

## Running the tool

**Runner (recommended for examples):**
```sh
uv run run-examples                       # run all examples (incremental)
uv run run-examples CCR2023.1.004.KATH    # run one example
uv run run-examples --force               # rerun everything
uv run run-examples --force-convert       # only force the convert step
uv run run-examples --fix                 # apply simple source fixes before compiling
```

Output goes to `output/<article-id>/` at the project root, with `prepare/` and `convert/` subdirectories containing logs and status.json files.

**Direct conversion (single file):**
```sh
uv run latex-jats path/to/main.tex path/to/output.xml --html
uv run latex-jats path/to/main.tex --zip   # also generate publisher-format zip
```

Pass `--html` to also generate `<doi-suffix>.html` alongside a copy of `jats-preview.css`.
Pass `--zip` to generate a publisher-format zip (ID/ID.xml, ID/ID.pdf, ID/ID_figN.ext).

**Web service:**
```sh
npm start                            # start both backend and frontend (requires npm install first)
npm run start:api                    # backend only (FastAPI on port 8000)
npm run start:web                    # frontend only (Vite dev server on port 5173)
```

Install dependencies: `uv sync --extra web` for the backend, `npm install` in root (for concurrently) and `npm run install:frontend` for the React frontend. Copy `.env.dev.example` to `.env` and fill in ORCID sandbox credentials (see comments in that file). The SQLite database, migrations, and file storage are created automatically under `storage/` on first startup. Swagger UI is available at `http://localhost:8000/docs`.

**Other CLI tools:**
```sh
uv run fixbib bibliography.bib            # clean up bibliography file
uv run fix-input main.tex                 # resolve \input{} commands
uv run prepare-source path/to/dir/        # validate and compile LaTeX source
uv run check-zip output.zip              # verify publisher-ready zip files
```

## Pipeline

Three sequential steps in `src/latex_jats/convert.py`:

1. **`latexmlc`** (`run_latexmlc`) — converts `.tex` to LaTeXML intermediate XML (`ltx:` namespace) using custom bindings from `src/latexml/`.
2. **`latexmlpost`** — applies LaTeXML's post-processors (bibliography scan, CrossRef citation linking) and the JATS XSLT to produce raw JATS XML.
3. **Python post-processing** — a chain of fixup functions run on the JATS XML in order:
   - `sanitize_ids` — cleans up XML IDs for JATS compliance
   - `fix_citation_ref_types` — adds `ref-type="bibr"` to in-text citation xrefs
   - `fix_metadata` — injects journal-meta (CCR constants) and article-meta (DOI, volume, issue, fpage, pub-date) from the LaTeX preamble; also trims whitespace from `<kwd>` elements
   - `fix_table_in_p` — unwraps `<table-wrap>` incorrectly nested inside `<p>`
   - `fix_fig_structure` — unwraps a stray `<p>` around a lone `<graphic>` inside `<fig>` (happens with `\makebox{\includegraphics{…}}` in the source); warns on any other deviation from the known-good `<fig>` shape (Ingenta/AUP will fail to render otherwise)
   - `fix_table_notes` — moves stray `<p>` inside `<table-wrap>` into a `<table-wrap-foot>`
   - `warn_tfoot_notes` — warns about notes placed inside `\tfoot` rows
   - `clean_body` — removes empty `<p>` elements and misplaced `<title>` inside `<body>`
   - `fix_nested_p` — unwraps illegal `<p>` nested inside `<p>`
   - `fix_disp_formula_in_list_item` — fixes display formulas inside list items
   - `fix_appendix_labels` — relabels tables/figures in appendices (Table A1, Figure B1, etc.)
   - `fix_footnotes` — moves inline footnotes into an `<fn-group>` in back matter
   - `fix_xref_ref_types` — sets correct `ref-type` on cross-reference xrefs
   - `fix_references` — repairs bibliography entries using the `.bbl` file (if available)
   - `fix_lstlisting_labels` — fixes labels/captions on code listings
   - `fix_ext_links` — normalizes `<ext-link>` URLs
   - `fix_pdf_graphic_refs` — rewrites `.pdf` graphic hrefs to `.svg`
   - `finalize_xml` — final cleanup (XML declaration, whitespace normalization)

   After post-processing, PDF figures are converted to SVG using inkscape, and graphics are renamed to publisher format (`ID_fig1.ext`, etc.).

**HTML preview** (`convert_to_html`) — applies `src/xslt/main/jats-html.xsl` (NLM JATS-to-HTML stylesheet) and copies `src/css/jats-preview.css` to the output directory.

## Design principles

- **Fix issues at the source, not post-hoc.** Prefer fixing conversion problems in the LaTeXML bindings (`ccr.cls.ltxml`, `biblatex.sty.ltxml`) or the XSLT wrapper over adding Python post-processing fixups. Post-processing should be reserved for things that genuinely cannot be handled earlier in the pipeline.
- **Warn, don't silently fix, bad LaTeX.** If the source `.tex` is incorrect or ambiguous (e.g. bare `>` in text mode, missing `\label`), do not try to guess the author's intent during conversion. Instead, emit a warning via `logging` so the author can fix the source. This is important because the tool will be author-facing.
- **Use `logging`, not `print`.** All messages that are relevant to the article author (warnings about source issues, conversion notes) must use `logging.warning` or `logging.info` so a future web frontend can collect and display them. The `logging.basicConfig` call in `main()` ensures CLI output still works.

## Repository structure

```
src/
  latex_jats/
    convert.py        main pipeline: convert() function and all fixup functions
    runner.py         incremental build runner for examples (run-examples CLI)
    prepare_source.py validates and compiles LaTeX (prepare-source CLI)
    fixbib.py         standalone bibliography cleaner (fixbib CLI)
    fix_input.py      resolves \input{} commands for the converter (fix-input CLI)
    check_zip.py      publisher-ready zip validator (check-zip CLI)
  latexml/
    ccr.cls.ltxml       LaTeXML bindings for ccr.cls (authors, abstract, keywords, metadata macros)
    biblatex.sty.ltxml  LaTeXML bindings for biblatex (citation labels, bibliography)
    fontspec.sty.ltxml  bindings for fontspec/newfontfamily (XeTeX Unicode font support)
    booktabs.sty.ltxml, longtable.sty.ltxml, tabu.sty.ltxml, threeparttablex.sty.ltxml
                        table package bindings
    adjustbox.sty.ltxml, luainputenc.sty.ltxml  miscellaneous package bindings
    arabtex.sty.ltxml, cjhebrew.sty.ltxml  stubs that warn about unsupported transliteration
  xslt/
    main/jats-html.xsl  NLM JATS-to-HTML preview stylesheet
    citations-prep/     citation formatting stylesheets
    post/, prep/        other XSLT helpers
  css/
    jats-preview.css  HTML proof preview stylesheet (copied to output alongside <doi-suffix>.html)
    LaTeXML.css, ltx-article.css  (used by LaTeXML's own HTML output, not the proof preview)
tests/
  conftest.py
  test_metadata.py             unit tests for fix_metadata
  test_clean_body.py           unit tests for clean_body
  test_fix_footnotes.py        unit tests for fix_footnotes
  test_fix_table_notes.py      unit tests for fix_table_notes
  test_fix_nested_p.py         unit tests for fix_nested_p
  test_fix_appendix_labels.py  unit tests for fix_appendix_labels
  test_fix_disp_formula.py     unit tests for fix_disp_formula_in_list_item
  test_fix_references.py       unit tests for fix_references
  test_fix_xref_ref_types.py   unit tests for fix_xref_ref_types
  test_fix_ext_links.py        unit tests for fix_ext_links
  test_fix_listing_data.py     unit tests for fix_listing_data
  test_fix_input.py            unit tests for fix_input
  test_warn_tfoot.py           unit tests for warn_tfoot_notes
  test_warn_fig_paragraphs.py  unit tests for figure paragraph warnings
  test_prepare_source.py       unit tests for prepare_source
  test_web_api.py              unit tests for the FastAPI backend (uses TestClient + in-memory SQLite)
  test_integration.py          integration tests (full pipeline via latexmlc)
  fixtures/latex/              minimal .tex files used by integration tests
examples/
  CCR2023.1.004.KATH/     each example has main.tex + source files directly in the folder
  CCR2025.1.2.YAO/        example article
output/                   centralized output tree (gitignored), also the Netlify deploy dir
  <article-id>/
    prepare/              compilation logs + status.json
    convert/              JATS XML, HTML, PDF, images + status.json
  index.html              generated preview index with status indicators
web/
  backend/
    app/
      main.py             FastAPI app, CORS, lifespan
      models.py           SQLModel tables (Manuscript, ManuscriptAuthor, AccessToken)
      config.py           AuthConfig from env vars (ORCID, OJS, session settings)
      deps.py             get_session / get_storage / get_current_user / get_current_role / require_editor
      storage.py          file storage abstraction (local filesystem, S3-ready interface)
      worker.py           background pipeline runner (prepare → convert → zip)
      ojs.py              OJS REST client (editor lookup, production submissions, DOI extraction)
      orcid.py            ORCID OAuth code exchange
      routes/             manuscripts.py, upload.py, status.py, download.py, output.py, auth.py, ojs.py
    alembic/              database migrations (auto-run on startup)
    alembic.ini
  frontend/               Vite + React + TypeScript + shadcn/ui SPA
    src/
      auth/               AuthContext (ORCID login state, role)
      api/                typed API client (client.ts, types.ts)
      pages/              DashboardPage, ManuscriptPage, PreviewPage
      components/         Layout, StatusBadge, UploadZone, LogViewer, CreateManuscriptDialog
      components/ui/      base-ui/shadcn primitives (badge, button, card, dialog, input, label, table)
deploy/
  docker-compose.yml        production compose (pre-built images, attached to releases)
  docker-compose.build.yml  build overlay for local image builds
  .env.example              production env template (attached to releases as .env)
  update.sh                 helper script for pulling updates on VPS
storage/                    runtime file storage (gitignored) — manuscripts/<doi_suffix>/source|output
```

## Authentication and access control

- **ORCID login** — any ORCID user can log in. Role (editor vs author) is derived per-request by comparing the user's ORCID against the OJS editor set (cached from `fetch_editor_orcids`). Dev override via `OJS_EDITOR_OVERRIDE_ORCIDS`.
- **Editors** see all manuscripts and can create/import new ones from OJS.
- **Authors** see only manuscripts where their ORCID appears in `ManuscriptAuthor`. Denied access returns 404 (not 403) to avoid leaking manuscript existence.
- **`require_editor`** dependency gates editor-only endpoints (manuscript creation, OJS import).
- **OJS integration** — editors import manuscripts from OJS copyediting stage (stageId 4). Import populates `ManuscriptAuthor` rows (with ORCIDs), title, abstract, keywords, DOI, volume, issue, year. The submissions list is cached for 60s.
- The frontend UI component library uses `@base-ui/react`, not Radix. Use `render` prop (not `asChild`) for composition and `buttonVariants()` for link-styled buttons.

## Database

SQLite via SQLModel. Alembic migrations in `web/backend/alembic/versions/`. Migrations run automatically on startup (`alembic upgrade head` in `_init_db_schema`). For a fresh DB the full migration chain runs; for an already-current DB it's a no-op. Pre-alembic DBs (tables but no `alembic_version` row) require a manual `alembic stamp <revision>`.

When adding new columns or tables, create a new migration in `web/backend/alembic/versions/` following the `0001`/`0002`/`0003` naming convention. Use `batch_alter_table` for SQLite compatibility.

## Releasing

Bump version in `pyproject.toml`, commit, then tag and push:

```sh
git tag v0.2.0
git push origin v0.2.0
```

CI builds and pushes Docker images (`ccsamsterdam/latex-jats-api`, `ccsamsterdam/latex-jats-caddy`) on `v*` tags.

## Syncing the CCR class pin

The prepare step warns authors when their vendored `ccr.cls` is older than, or differs from, the latest upstream release at [ccr-journal/ccr-latex](https://github.com/ccr-journal/ccr-latex). "Latest" is defined by two pinned constants in `src/latex_jats/ccr_cls.py` — `EXPECTED_CCR_CLS_VERSION` and `EXPECTED_CCR_CLS_SHA256` — plus a committed canonical copy at `tests/fixtures/ccr_canonical.cls`.

When upstream releases a new version, bump all three together:

1. Replace `tests/fixtures/ccr_canonical.cls` with the new upstream file (`curl -fsSL https://raw.githubusercontent.com/ccr-journal/ccr-latex/main/ccr.cls -o tests/fixtures/ccr_canonical.cls`).
2. Update `EXPECTED_CCR_CLS_VERSION` in `src/latex_jats/ccr_cls.py` to match the new `% Version X.XX` comment in the file.
3. Recompute the hash and update `EXPECTED_CCR_CLS_SHA256`:
   ```sh
   uv run python -c "from latex_jats.ccr_cls import compute_ccr_cls_sha256; \
     import pathlib; print(compute_ccr_cls_sha256(pathlib.Path('tests/fixtures/ccr_canonical.cls')))"
   ```
4. Run `uv run pytest tests/test_ccr_cls.py`. The `test_canonical_fixture_matches_pinned_hash` self-check fails loudly if the fixture and pins diverge, so you'll know immediately if any of the three got skipped.

## Tests

Run the tests with:

```sh
uv run pytest                        # all tests (integration tests require latexmlc)
uv run pytest -m "not integration"   # unit tests only
uv run pytest -m integration         # integration tests only
```

Integration tests are skipped automatically if `latexmlc` is not installed.

**When to add tests:**

- Every new Python post-processing function in `convert.py` should have unit tests in a corresponding `tests/test_<function>.py` file, following the pattern in `test_metadata.py` and `test_fix_table_notes.py` (write minimal XML to a temp file, call the function, parse the result, assert on the tree).
- Every new LaTeXML binding feature (new macro or constructor in `ccr.cls.ltxml` or `biblatex.sty.ltxml`) should have an integration test in `test_integration.py`. Reuse existing fixture `.tex` files where possible, or add a new minimal fixture under `tests/fixtures/latex/`.
- The `authors.tex` fixture is a good general-purpose base: it exercises authors, affiliations, abstract, keywords, and a bibliography. Use it for tests that need a complete front matter.
- New FastAPI routes should have tests in `tests/test_web_api.py`, using `TestClient` with dependency overrides for `get_session` (in-memory SQLite with `StaticPool`) and `get_storage` (`tmp_path`). See existing tests there for the pattern.
- The test suite has an `autouse` fixture that pins `fetch_editor_orcids` to return `{EDITOR_ORCID}` so role checks don't hit the network. OJS production submissions are injected via `ojs_client.set_production_submissions_override([...])`. Both are reset between tests.
- Auth tests are in `tests/test_auth.py` (ORCID callback flow, session management). OJS client tests in `tests/test_ojs_client.py` (uses `respx` to mock HTTP).
