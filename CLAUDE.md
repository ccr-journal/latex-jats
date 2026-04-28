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
uv run jatsmith path/to/main.tex path/to/output.xml --html
uv run jatsmith path/to/main.tex --zip   # also generate publisher-format zip
```

Pass `--html` to also generate `<doi-suffix>.html` alongside a copy of `jats-preview.css`.
Pass `--zip` to generate a publisher-format zip (ID/ID.xml, ID/ID.pdf, ID/ID_figN.ext).

**Web service:**
```sh
npm start                            # start both backend and frontend (requires npm install first)
npm run start:api                    # backend only (FastAPI on port 8000)
npm run start:web                    # frontend only (Vite dev server on port 5173)
```

Install dependencies: `npm install` in root (for concurrently), then `npm run install:backend` (wraps `uv sync --extra web`) and `npm run install:frontend` for the React frontend. Copy `.env.dev.example` to `.env` — the defaults include `EDITOR_CREDENTIALS=editor:devpass` so you can log in immediately. The SQLite database, migrations, and file storage are created automatically under `storage/` on first startup. Swagger UI is available at `http://localhost:8000/docs`.

**Other CLI tools:**
```sh
uv run fixbib bibliography.bib            # clean up bibliography file
uv run fix-input main.tex                 # resolve \input{} commands
uv run prepare-source path/to/dir/        # validate and compile LaTeX source
uv run check-zip output.zip              # verify publisher-ready zip files
```

## Pipeline

Three sequential steps in `src/jatsmith/convert.py`:

1. **`latexmlc`** (`run_latexmlc`) — converts `.tex` to LaTeXML intermediate XML (`ltx:` namespace) using custom bindings from `src/latexml/`.
2. **`latexmlpost`** — applies LaTeXML's post-processors (bibliography scan, CrossRef citation linking) and the JATS XSLT to produce raw JATS XML.
3. **Python post-processing** — a chain of fixup functions run on the JATS XML in order:
   - `sanitize_ids` — cleans up XML IDs for JATS compliance
   - `dedupe_ref_lists` — drops orphan `<ref-list>` elements when biber emitted multiple `\datalist` blocks. With `biblatex[sortcites=true]` (which `ccr.cls` uses), biber 2.19+ writes one `\datalist` per registered list (one for the bibliography, one for citation-group sorting); LaTeXML emits each as a separate `<ltx:bibliography>` and `MakeBibliography` produces duplicate `<ref-list>`. The dedupe keeps the list whose IDs are referenced by body `<xref rid>` and drops the rest. biber ≤ 2.17 collapsed the lists into one and didn't trigger this.
   - `fix_citation_ref_types` — adds `ref-type="bibr"` to in-text citation xrefs
   - `fix_metadata` — injects journal-meta (CCR constants) and article-meta (DOI, volume, issue, fpage, pub-date) from the LaTeX preamble; also trims whitespace from `<kwd>` elements
   - `collapse_affiliations` — deduplicates identical `<aff>` elements emitted by LaTeXML (one per author) and rewrites them as id-linked siblings of `<contrib>` inside `<contrib-group>` (Edify "Style 2"). Each `<contrib>` gets a `<xref ref-type="aff" rid="affN"/>`; unique `<aff id="affN">` elements are appended to `<contrib-group>` in first-occurrence order.
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
   - `fix_supplementary_material` — lifts ccr-suppmat markers into `<supplementary-material>` elements in `<article-meta>` using the first inner `<ext-link>`'s URL for `xlink:href`; the marker is unwrapped in place so its text still renders in the body paragraph or footnote. Two marker shapes are recognized, one per authoring path: `<styled-content style-type="ccr-suppmat">` from the LaTeX pipeline (`\supplementarymaterial{…}` via `ccr.cls.ltxml` + wrapper XSLT) and `<named-content content-type="ccr-suppmat">` from the Quarto pipeline (`[…]{.ccr-suppmat}` spans emitted by Pandoc's JATS writer). IDs are `suppmat1`, `suppmat2`, … to avoid colliding with body section IDs (`S1`, `S2`, …). Shared between both pipelines.
   - `strip_mathml_alttext` — drops `@alttext` from `<mml:math>` (Ingenta re-serializes it unescaped)
   - `normalize_mathml_chars` — rewrites Mathematical Alphanumeric Symbols (U+1D400–U+1D7FF) to `mathvariant` + BMP char, so Ingenta's Java parser doesn't re-serialize them as invalid surrogate char references (`&#55349;`)
   - `fix_pdf_graphic_refs` — rewrites `.pdf` graphic hrefs to `.svg`
   - `finalize_xml` — final cleanup (XML declaration, whitespace normalization); warns if any supplementary-plane chars survived

   After post-processing, PDF figures are converted to SVG using inkscape, and graphics are renamed to publisher format (`ID_fig1.ext`, etc.).

**HTML preview** (`convert_to_html`) — applies `src/xslt/main/jats-html.xsl` (NLM JATS-to-HTML stylesheet) and copies `src/css/jats-preview.css` to the output directory.

## Ingenta Edify XML guidelines

Ingenta sent us their authoritative JATS XML specification for Edify in April 2026 as two PDFs (`xml_guide.pdf` and `xml_guide_media.pdf`). Both files, and a combined markdown transcription at [xml_guide.md](xml_guide.md), are kept locally. **Do not commit the PDFs and do not share them outside the project** — we haven't yet received permission to publish them. The markdown transcription is our working reference; prefer reading it over re-parsing the PDFs. If Ingenta ships a revised spec, replace both the PDFs and [xml_guide.md](xml_guide.md) together so they stay in sync.

The guide is the source of truth when deciding what JATS shapes to emit. A few constraints that already matter for this pipeline: `<contrib>` elements with any `contrib-type` other than `"author"` are silently ignored by Edify; `<fig>` and `<table-wrap>` both require an `@id`; only one `<ref-list>` is allowed in `<back>`; `<nlm-citation>` is deprecated (use `element-citation` or `mixed-citation`); `self-uri/@xlink:href` must match the PDF filename exactly with no folder prefix; and `<aff>` elements must live either nested inside `<contrib>` (Style 1) or as siblings of `<contrib>` inside `<contrib-group>` (Style 2) — placing them outside `<contrib-group>` silently drops them on the rendered site (the URMA submission failure). Both pipelines emit Style 2 via `collapse_affiliations` (LaTeX) / `group_affiliations` (Quarto); see memory note `project_aup_affiliation_shape` for the empirical backstory.

## Design principles

- **Fix issues at the source, not post-hoc.** Prefer fixing conversion problems in the LaTeXML bindings (`ccr.cls.ltxml`, `biblatex.sty.ltxml`) or the XSLT wrapper over adding Python post-processing fixups. Post-processing should be reserved for things that genuinely cannot be handled earlier in the pipeline.
- **Warn, don't silently fix, bad LaTeX.** If the source `.tex` is incorrect or ambiguous (e.g. bare `>` in text mode, missing `\label`), do not try to guess the author's intent during conversion. Instead, emit a warning via `logging` so the author can fix the source. This is important because the tool will be author-facing.
- **Use `logging`, not `print`.** All messages that are relevant to the article author (warnings about source issues, conversion notes) must use `logging.warning` or `logging.info` so a future web frontend can collect and display them. The `logging.basicConfig` call in `main()` ensures CLI output still works.

## Repository structure

```
src/
  jatsmith/
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
      models.py           SQLModel tables (Manuscript, ManuscriptAuthor, AccessToken, ManuscriptToken)
      config.py           AuthConfig from env vars (EDITOR_CREDENTIALS, OJS, session settings)
      deps.py             get_session / get_storage / get_current_user / get_current_role / require_editor
      storage.py          file storage abstraction (local filesystem, S3-ready interface)
      worker.py           background pipeline runner (prepare → convert → zip)
      ojs.py              OJS REST client (production submissions, metadata sync)
      routes/             manuscripts.py, upload.py, status.py, download.py, output.py, auth.py, ojs.py
    alembic/              database migrations (auto-run on startup)
    alembic.ini
  frontend/               Vite + React + TypeScript + shadcn/ui SPA
    src/
      auth/               AuthContext (login state, role)
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

- **Editor login** — editors sign in with username + password via `POST /api/auth/login`. Credentials come from the `EDITOR_CREDENTIALS` env var: a plain string creates a single `editor` user with that password, or use `user1:pw1,user2:pw2` for multiple accounts. A successful login mints an `AccessToken` row; the role is trivially "editor" whenever an `AccessToken` is presented.
- **Author access** — authors use per-manuscript `ManuscriptToken` links (emailed or copy-pasted by the editor). A valid `ManuscriptToken` grants role="author" scoped to exactly one manuscript. Denied access returns 404 (not 403) to avoid leaking manuscript existence.
- **`require_editor`** dependency gates editor-only endpoints (manuscript creation, OJS import, sync).
- **OJS integration** — editors import manuscripts from OJS copyediting stage (stageId 4). Import populates `ManuscriptAuthor` rows, title, abstract, keywords, DOI, volume, issue, year. The submissions list is cached for 60s. OJS calls use the service-account `OJS_ADMIN_TOKEN` and are independent of the editor's identity.
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

CI builds and pushes Docker images (`ccsamsterdam/jatsmith-api`, `ccsamsterdam/jatsmith-caddy`) on `v*` tags.

## Syncing the CCR extension bundle

The prepare step warns authors when their vendored CCR Quarto extension — `ccr.cls`, `ccrtemplate.tex`, partials, `_extension.yml`, etc. — drifts from the canonical copy. Everything in that directory is publishing-toolchain infrastructure, not author content; customizations belong in the document, not the extension. The canonical bundle lives at `src/jatsmith/ccr_canonical_extension/` and is shipped inside the Python package so the web UI's "Use most recent ccr.cls" toggle can install it into a workspace (via `install_canonical_ccr_extension`).

`src/jatsmith/ccr_cls.py` derives its pins at import time:

- `EXPECTED_CCR_CLS_VERSION` — the `% Version X.XX` comment in `ccr.cls`.
- `EXPECTED_CCR_CLS_SHA256` — hash of `ccr.cls` alone (after CRLF→LF normalization).
- `EXPECTED_EXTENSION_SHA256` — hash of the whole bundle (paths + normalized contents).

When upstream releases a new version, refresh the canonical bundle from [ccr-journal/ccr-quarto](https://github.com/ccr-journal/ccr-quarto):

```sh
rm -rf src/jatsmith/ccr_canonical_extension
cp -r ~/path/to/ccr-quarto/_extensions/ccr src/jatsmith/ccr_canonical_extension
```

The `% Version X.XX` comment and `\ProvidesClass[...vX.XX]` tag inside `ccr.cls` are the source of truth for the class version. Run `uv run pytest tests/test_ccr_cls.py` — `test_canonical_providesclass_matches_version_comment` fails if those two tags disagree, and `test_canonical_bundle_has_expected_files` fails if anyone accidentally drops a partial or the class file from the bundle.

Note: until in-flight changes land upstream, the canonical bundle may be ahead of `ccr-journal/ccr-quarto` on specific files (e.g. a new partial, a newer `ccr.cls`). When resyncing, make sure you don't regress those additions.

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
- The test suite has an `autouse` fixture that pins the auth config (with a known `editor_credentials` map) so tests don't depend on env vars. OJS production submissions are injected via `ojs_client.set_production_submissions_override([...])` and reset between tests.
- Auth tests are in `tests/test_auth.py` (password login flow, session management). The `author_client` fixture in `test_web_api.py` is authed via `ManuscriptToken` (role=author) and used to assert 403s on editor-only endpoints.
