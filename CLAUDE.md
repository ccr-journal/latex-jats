# CLAUDE.md

## Project overview

This tool converts CCR (Computational Communication Research) journal articles from LaTeX to JATS XML for submission to the AUP Online publishing platform. It uses LaTeXML with custom bindings and a Python post-processing pipeline, and can optionally produce an HTML proof preview.

The end goal is to turn this into a web service where authors can upload their LaTeX source and check the conversion status themselves.

## Running the tool

```sh
uv run latex-jats examples/CCR2023.1.004.KATH/latex/main.tex
uv run latex-jats path/to/main.tex path/to/output.xml --html
```

Output defaults to `<article-dir>/output/<doi-suffix>.xml` (derived from the `\doi{}` macro in the LaTeX preamble). Pass `--html` to also generate `<doi-suffix>.html` alongside a copy of `jats-preview.css`.

## Pipeline

Three sequential steps in `src/latex_jats/convert.py`:

1. **`latexmlc`** (`run_latexmlc`) — converts `.tex` to LaTeXML intermediate XML (`ltx:` namespace) using custom bindings from `src/latexml/`.
2. **`latexmlpost`** — applies LaTeXML's post-processors (bibliography scan, CrossRef citation linking) and the JATS XSLT to produce raw JATS XML.
3. **Python post-processing** — a chain of fixup functions run on the JATS XML in order:
   - `fix_citation_ref_types` — adds `ref-type="bibr"` to in-text citation xrefs
   - `fix_metadata` — injects journal-meta (CCR constants) and article-meta (DOI, volume, issue, fpage, pub-date) from the LaTeX preamble; also trims whitespace from `<kwd>` elements
   - `fix_table_notes` — moves stray `<p>` inside `<table-wrap>` into a `<table-wrap-foot>`
   - `clean_body` — removes empty `<p>` elements and misplaced `<title>` inside `<body>`
   - `fix_footnotes` — moves inline footnotes into an `<fn-group>` in back matter

**HTML preview** (`convert_to_html`) — applies `src/xslt/main/jats-html.xsl` (NLM JATS-to-HTML stylesheet) and copies `src/css/jats-preview.css` to the output directory.

## Design principles

- **Fix issues at the source, not post-hoc.** Prefer fixing conversion problems in the LaTeXML bindings (`ccr.cls.ltxml`, `biblatex.sty.ltxml`) or the XSLT wrapper over adding Python post-processing fixups. Post-processing should be reserved for things that genuinely cannot be handled earlier in the pipeline.
- **Warn, don't silently fix, bad LaTeX.** If the source `.tex` is incorrect or ambiguous (e.g. bare `>` in text mode, missing `\label`), do not try to guess the author's intent during conversion. Instead, emit a warning via `logging` so the author can fix the source. This is important because the tool will be author-facing.
- **Use `logging`, not `print`.** All messages that are relevant to the article author (warnings about source issues, conversion notes) must use `logging.warning` or `logging.info` so a future web frontend can collect and display them. The `logging.basicConfig` call in `main()` ensures CLI output still works.

## Repository structure

```
src/
  latex_jats/
    convert.py        main pipeline: all conversion and fixup functions
    fixbib.py         standalone bibliography cleaner
  latexml/
    ccr.cls.ltxml     LaTeXML bindings for ccr.cls (authors, abstract, keywords, metadata macros)
    biblatex.sty.ltxml  LaTeXML bindings for biblatex (citation labels, bibliography)
  xslt/
    main/jats-html.xsl  NLM JATS-to-HTML preview stylesheet
    citations-prep/     citation formatting stylesheets
    post/, prep/        other XSLT helpers
  css/
    jats-preview.css  HTML proof preview stylesheet (copied to output alongside <doi-suffix>.html)
    LaTeXML.css, ltx-article.css  (used by LaTeXML's own HTML output, not the proof preview)
tests/
  conftest.py
  test_metadata.py        unit tests for fix_metadata (journal-meta, article-meta, kwd trimming)
  test_clean_body.py      unit tests for clean_body
  test_fix_footnotes.py   unit tests for fix_footnotes
  test_fix_table_notes.py unit tests for fix_table_notes
  test_integration.py     integration tests (full pipeline via latexmlc)
  fixtures/latex/         minimal .tex files used by integration tests
examples/
  CCR2023.1.004.KATH/     reference article with latex/ input and output/ JATS+HTML
  CCR2025.1.2.YAO/        article with gold/ JATS XML from the typesetting company for comparison
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
