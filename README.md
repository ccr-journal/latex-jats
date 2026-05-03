# JATSmith

Convert LaTeX and Quarto manuscripts to publisher-ready JATS XML, with HTML and PDF previews. Ships with a self-hosted web app for editors and authors to upload sources, run conversions, review the result, and approve. Optional [OJS](https://pkp.sfu.ca/software/ojs/) integration for journals that use it.

JATSmith was first built for [Computational Communication Research (CCR)](https://computationalcommunication.org) but is designed to host other journals — see [Adapting to a different journal](#adapting-to-a-different-journal) below.

## Quick start

### Stand up the web service (production)

```sh
mkdir jatsmith && cd jatsmith
wget -q https://github.com/ccr-journal/jatsmith/releases/latest/download/{docker-compose.yml,.env}
# edit .env — at minimum set EDITOR_CREDENTIALS and SITE_ADDRESS
docker compose up -d
```

This starts two containers (Caddy + FastAPI api) with TLS handled automatically when `SITE_ADDRESS` is a public domain. Data lives in the `app_storage` Docker volume; database migrations run on startup. See [deploy/.env.example](deploy/.env.example) for every option.

Open the site, log in with one of the `EDITOR_CREDENTIALS` pairs, and complete the **Site Config** form on first run (journal name, ISSN, license, optional canonical class-file URL). The dashboard then accepts uploads.

### Try it locally

```sh
git clone https://github.com/ccr-journal/jatsmith && cd jatsmith
npm install
npm run install:backend          # uv sync --extra web
npm run install:frontend
cp .env.dev.example .env         # default editor login: editor / devpass
npm start                         # backend on :8000, frontend on :5173
```

Swagger UI: <http://localhost:8000/docs>.

### Convert one file from the CLI

The CLI is mainly for debugging the conversion of a single source tree.

```sh
# Install LaTeXML + jing (one-time, system-wide)
sudo apt install cpanminus libxml2-dev libxslt1-dev libdb-dev jing
sudo cpanm --notest LaTeXML

# Install the Python package
uv sync

# Convert
uv run jatsmith path/to/main.tex                       # → <article>/output/main.xml
uv run jatsmith path/to/main.qmd out.xml --html        # explicit output + HTML preview
uv run jatsmith path/to/main.tex --zip                 # also build a publisher-format zip
```

Output is validated against the [JATS Publishing 1.2 RelaxNG schema](https://jats.nlm.nih.gov/publishing/1.2/rng.html) (MathML3 variant) automatically. You can also validate online with the [J4R Validator](https://j4r.nlm.nih.gov/) or [PMC StyleChecker](https://pmc.ncbi.nlm.nih.gov/tools/stylechecker/).


## Adapting to a different journal

Three customization touchpoints, in increasing order of effort.

### 1. Journal identity (in-app form)

After first login, the editor confirms the journal's identity in the **Site Config** form (also `PUT /api/site-config`):

- Journal name, journal-id, ISSN(s)
- Publisher name & location, copyright/license text
- DOI prefix (used to derive document IDs from full DOIs)
- Branding (site name, header text, markdown landing-page description)

These values flow into JATS `<journal-meta>`/`<permissions>` for every conversion. Defaults are placeholder values until the editor saves the form for the first time.

### 2. Canonical class file & Quarto extension (in-app form)

Two optional URL fields in the same form let JATSmith fetch and cache the journal's canonical class file & Quarto extension on app start (and re-fetch when the URLs change):

- **`class_file_url`** — direct URL to the LaTeX class file. GitHub `blob/...` HTML URLs and `raw.githubusercontent.com/...` URLs both work. Example: `https://github.com/ccr-journal/ccr-latex/blob/main/ccr.cls`.
- **`quarto_extension_repo`** — `<owner>/<repo>[@<ref>]` shorthand matching `quarto add`. Example: `ccr-journal/ccr-quarto` or `ccr-journal/ccr-quarto@v0.5`.

Either or both may be empty. When set, each manuscript page shows a **Use latest …** toggle: turning it on overwrites the author's vendored class/extension with the canonical copy before conversion. Drift warnings fire automatically when an author's copy is outdated or hand-edited.

The fetched bundle is cached at `STORAGE_DIR/canonical/`; network failures fall back to the previous cache so a transient GitHub blip doesn't take the feature down.

### 3. Custom LaTeXML class binding (small Python file)

LaTeXML ships handlers for `article.cls` and the standard packages out of the box. Vanilla LaTeX classes therefore work with no extra effort. If your journal uses a custom class with non-standard frontmatter macros (`\title{…}`, `\author{…}`, `\section{…}` are fine; things like `\editorialstaff{…}`, `\doi{…}`, `\acknowledgements{…}`, etc. are not), you'll need a small LaTeXML binding.

[`src/latexml/ccr.cls.ltxml`](src/latexml/ccr.cls.ltxml) is a worked example: ~10 frontmatter macros, an `\abstract` environment, and a few defensive stubs for macros LaTeXML doesn't need to render. Copy it, replace the macro definitions with your journal's, and either ship it inside your custom class repo (LaTeXML auto-loads a `<name>.cls.ltxml` next to `<name>.cls`) or vendor it under `src/latexml/`.

The other files under [`src/latexml/`](src/latexml/) — `biblatex.sty.ltxml`, `booktabs.sty.ltxml`, `longtable.sty.ltxml`, `threeparttable[x].sty.ltxml`, `tabu.sty.ltxml`, `fontspec.sty.ltxml`, `adjustbox.sty.ltxml`, etc. — are general-purpose package bindings that benefit any journal using those packages. They don't need changes for a new class.


## Pipeline

The LaTeX path runs three steps:

1. **`latexmlc`** ([`run_latexmlc`](src/jatsmith/convert.py)) — converts `.tex` to LaTeXML's intermediate XML using the bindings in [`src/latexml/`](src/latexml/). The `biblatex.sty.ltxml` binding loads `.bbl` and builds author-year citation labels.
2. **`latexmlpost`** — runs LaTeXML's bibliography-resolution and the JATS XSLT to produce raw JATS XML.
3. **Python post-processing** — a chain of fixups for structural/semantic issues (citation ref-types, affiliation grouping, table notes, footnotes, supplementary material, MathML normalization, …). See `convert.py` for the full list.

The Quarto path delegates rendering to `quarto render --to jats_publishing` and then runs a parallel set of fixups so Quarto and LaTeX produce convergent JATS shapes.

After post-processing, PDF figures are converted to SVG (inkscape) and graphics are renamed to publisher format (`ID/ID_figN.ext`). An optional HTML preview is produced via the NLM JATS-to-HTML stylesheet.


## Repository layout

```
src/jatsmith/        Python package — conversion pipeline + CLI tools
  convert.py           LaTeX → JATS pipeline (and post-processing fixups)
  quarto.py            Quarto → JATS pipeline
  prepare_source.py    LaTeX workspace + compile (prepare-source CLI)
  canonical_extension.py  Fetch & cache the journal's canonical class/extension
  site_config.py       SiteConfigData dataclass + DB loader (CLI fallback)
src/latexml/         LaTeXML bindings (.cls and .sty handlers)
src/xslt/            JATS-to-HTML stylesheet + helpers
src/css/             jats-preview.css for the HTML proof preview
web/backend/         FastAPI service (routes, models, alembic migrations, worker)
web/frontend/        Vite + React + TypeScript SPA (editor & author UIs)
deploy/              docker-compose stack + .env template (production)
tests/               unit + integration tests, fixture LaTeX files
```


## Tests

Unit tests cover Python post-processing, route handlers, and the canonical-bundle fetch/install flow. They require no external tools:

```sh
uv sync --extra test
uv run pytest -m "not integration"
```

Integration tests run the full LaTeX → JATS pipeline against fixture sources and require `latexmlc` (skipped automatically if missing):

```sh
uv run pytest -m integration
# or run everything at once:
uv run pytest
```

CI ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) runs both.


## Web service: deployment notes

### Releasing a new version

Pushing a `v*` tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which builds and pushes the `caddy` and `api` Docker images to Docker Hub and creates a GitHub release with the matching `docker-compose.yml` / `.env`.

```sh
# 1. Bump version in pyproject.toml, commit
# 2. Tag and push
git tag v0.9.0
git push origin v0.9.0
```

On the host, pull the new images and restart:

```sh
docker compose pull
docker compose up -d
```

### Rebuilding the api base image

The api image is split into a **base** (Ubuntu + TeX Live + LaTeXML + inkscape + poppler + uv, ~2.5 GB) and a thin **app image** on top (Python deps + source, ~100 MB). App releases reuse the base, so a host redeploy only pulls the small delta.

The base is rebuilt manually when a TeX Live refresh or Ubuntu security update is needed (every few months is typical). App releases pin a specific base tag in `web/backend/Dockerfile` so untested base refreshes don't sneak into app deploys.

```sh
TAG=2026-04   # convention: YYYY-MM
docker buildx build \
  --platform linux/amd64 \
  --tag ccsamsterdam/jatsmith-base:$TAG \
  --tag ccsamsterdam/jatsmith-base:latest \
  --push \
  -f web/backend/Dockerfile.base \
  web/backend/
```

Then update the `FROM` line in `web/backend/Dockerfile` to point at the new tag, commit, and tag a new app release.
