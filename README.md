## Overview

This is a tool to convert CCR journal articles in _latex_ format into _JATS XML_.

- it uses the [LaTeXML package](https://math.nist.gov/~BMiller/LaTeXML/) with custom bindings for `ccr.cls` and `biblatex`
- it does some post-processing of the JATS output

It can be used as a CLI tool (see below) or as a web service where editors and authors can upload LaTeX source, run the conversion, and preview/download results. The quickest way to get the web service running:

```sh
SITE_ADDRESS=jats.yourdomain.com docker compose up -d --build
```

See the [Web Service](#web-service) section for details.


### Processing pipeline

Running `latex-jats` automatically performs three steps:

1. **`latexmlc`** — processes the `.tex` file using the custom bindings in `src/latexml/` and produces LaTeXML intermediate XML (the `ltx:` namespace). The `biblatex.sty.ltxml` binding loads the `.bbl` file and builds author-year citation labels.
2. **`latexmlpost`** — runs LaTeXML's post-processors on the intermediate XML: scans the document, builds the bibliography, and runs CrossRef to resolve in-text citations to their bibliography entries (filling in `idref` attributes).
3. **XSLT + Python** — applies the LaTeXML JATS stylesheet (with a fix for given-name spacing in `ltx:personname`) to produce JATS XML, then runs Python post-processing steps to inject journal/article metadata from the LaTeX preamble and fix minor structural issues.

Optionally, the JATS output can be converted to HTML for checking proofs. This uses the NLM/JATS XSLT stylesheets and can be run separately with `latexmlpost --format=html`.

### Repository structure
- `src/latex_jats/` | Python package: main converter (`convert.py`) and bibliography cleaner (`fixbib.py`)
- `src/latexml/` | LaTeXML bindings: `ccr.cls.ltxml` and `biblatex.sty.ltxml`
- `src/lua/` | Pandoc Lua filter for metadata extraction (`ccr_latex.lua`)
- `src/css/` | Stylesheets for LaTeXML HTML preview output
- `examples/` | Reference JATS XML examples


## Installation and usage

### Installation

**1. Install LaTeXML 0.8.8** (the apt package is outdated — install via cpanm):

```sh
sudo apt install cpanminus libxml2-dev libxslt1-dev libdb-dev
sudo cpanm --notest LaTeXML
```

**2. Install [jing](https://relaxng.org/jclark/jing.html)** for JATS XML validation (RelaxNG):

```sh
sudo apt install jing
```

**3. Install the Python package** using [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

### Usage

```sh
# output goes automatically to <article>/output/main.xml
uv run latex-jats examples/CCR2023.1.004.KATH/latex/main.tex

# or specify an output path explicitly
uv run latex-jats examples/CCR2023.1.004.KATH/latex/main.tex path/to/output.xml
```

The output is automatically validated against the [JATS Publishing 1.2 RelaxNG schema](https://jats.nlm.nih.gov/publishing/1.2/rng.html) (MathML3 variant) using `jing`. You can also validate online with [J4R Validator](https://j4r.nlm.nih.gov/) or [PubMed Central Validator](https://pmc.ncbi.nlm.nih.gov/tools/stylechecker/).

<!--
These are words of wisdom, but I don't think they belong in the README

### check input

However, **before you do this**, check the input. Check the `.tex` files (these tend to be of the type `main.tex` containing a `body.tex`, sometimes with appendices and such). Also check the `.bib` files (`bibliography.bib`). These files can contain mistakes that will trip up the conversion. Run `fixbib` to clean up the bibliography.

`fixbib` is not included in the main script because it is expected that many irregularities will occur and need manual attention. It would also make debugging very difficult. So it is separate and expected to grow. (Several scripts that "check" biblatex and bibtex can be found on [Pypi](https://pypi.org/search/?q=biblatex) but none seems to do what was needed here).

For the correction of `.tex` files no script was created. Out of scope and the author's responsibility.

### bibliographies
JATS is not meant to support bibliographical style. Style support on the publication platform AUP Online is minimal. CCR's APA style is not supported. What is left is to manhandle the JATS into semi APA and be content with basic online rendering. Not worse than the PDFs produced so far, though.

Another file that is likely to grow is the biblatex binding `src/latexml/biblatex.sty.ltxml`. Not so much for bibliographical styling, but for unsupported tex tags in the articles.

### on the whole
Latex is a slippery beast, very different from XML. Authors do as they please. Expect continuous variety and surprises. Expect constant updating of the scripts. Do _not_ expect automatic conversion and a smooth workflow. Expect manual labor, the hallmark of a good editor.
-->

## Web Service

A web interface for editors and authors to upload LaTeX source, run the conversion pipeline, and preview/download results.

### Local development

Install dependencies:

```sh
uv sync --extra web              # Python backend
npm install                      # root (concurrently)
npm run install:frontend         # React frontend
```

Run the dev servers (backend on :8000, frontend on :5173):

```sh
npm start
```

Swagger UI is available at http://localhost:8000/docs.

### Docker deployment

```sh
# Build and start (set SITE_ADDRESS to your domain for automatic HTTPS)
SITE_ADDRESS=jats.example.com docker compose up -d --build

# Or run locally
docker compose up -d --build
```

This starts two containers:
- **caddy** — serves the React frontend and reverse-proxies `/api` to the backend; handles TLS certificates automatically when `SITE_ADDRESS` is set to a public domain
- **api** — FastAPI backend with the full conversion pipeline (TeX Live, LaTeXML, inkscape)

Data (SQLite database, uploaded manuscripts, conversion output) is stored in the `app_storage` Docker volume.

## Unit and Integration Tests

Unit tests cover the Python post-processing functions and require no external tools:

```sh
uv sync --extra test
uv run pytest -m "not integration"
```

Integration tests run the full LaTeX → JATS pipeline and require `latexmlc`:

```sh
uv run pytest -m integration
# or run everything at once:
uv run pytest
```

Integration tests are automatically skipped if `latexmlc` is not installed. The CI workflow (`.github/workflows/tests.yml`) runs both.
