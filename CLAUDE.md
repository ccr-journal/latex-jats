# CLAUDE.md

## Project overview

This tool converts CCR (Computational Communication Research) journal articles from LaTeX to JATS XML for submission to the AUP Online publishing platform. It uses LaTeXML with custom bindings and a Python post-processing pipeline, and can optionally produce an HTML proof preview.

A web service (see `website-design.md`) is being built on top of this pipeline, where editors and authors can upload LaTeX source and check the conversion status. The FastAPI backend skeleton is implemented in `web/backend/`; remaining steps are pipeline integration, frontend, auth, OJS integration, and Docker packaging.

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

**Web service (backend):**
```sh
uv run --extra web uvicorn web.backend.app.main:app --reload --port 8000
```

Install web dependencies first with `uv sync --extra web`. The SQLite database and file storage are created automatically under `storage/` on first startup. Swagger UI is available at `http://localhost:8000/docs`.

**Other CLI tools:**
```sh
uv run fixbib bibliography.bib            # clean up bibliography file
uv run fix-input main.tex                 # resolve \input{} commands
uv run prepare-source path/to/dir/        # validate and compile LaTeX source
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
  CCR2025.1.2.YAO/        article with gold/ JATS XML from the typesetting company for comparison
output/                   centralized output tree (gitignored), also the Netlify deploy dir
  <article-id>/
    prepare/              compilation logs + status.json
    convert/              JATS XML, HTML, PDF, images + status.json
  index.html              generated preview index with status indicators
web/
  backend/
    app/
      main.py             FastAPI app, CORS, lifespan
      deps.py             get_session / get_storage dependency callables
      models.py           SQLModel tables (Manuscript, ConversionJob, AccessToken)
      storage.py          file storage abstraction (local filesystem, S3-ready interface)
      routes/             manuscripts.py, upload.py, status.py, download.py
    alembic/              database migrations
    alembic.ini
storage/                  runtime file storage (gitignored) — manuscripts/<doi_suffix>/source|output
```

The `gold/` directory under CCR2025.1.2.YAO contains the JATS XML produced by the professional typesetting company. Use it as a reference when evaluating output quality. It may contain minor imperfections, so it does not need to be matched exactly. See `todo.md` in the project root for a tracked list of discrepancies.

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
