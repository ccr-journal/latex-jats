## short explanation

### overview

This is a tool to convert CCR journal articles in _latex_ format into _JATS XML_.

- it uses the [LaTeXML package](https://math.nist.gov/~BMiller/LaTeXML/) with custom bindings for `ccr.cls` and `biblatex`
- it does some post-processing of the JATS output

### installation

**1. Install LaTeXML 0.8.8** (the apt package is outdated — install via cpanm):

```sh
sudo apt install cpanminus libxml2-dev libxslt1-dev libdb-dev
sudo cpanm --notest LaTeXML
```

**2. Install the Python package** using [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

### usage

```sh
# output goes automatically to <article>/output/main.xml
uv run latex-jats examples/CCR2023.1.004.KATH/latex/main.tex

# or specify an output path explicitly
uv run latex-jats examples/CCR2023.1.004.KATH/latex/main.tex path/to/output.xml
```

We can validate the JATS file online with [J4R Validator](https://j4r.nlm.nih.gov/) or [PubMed Central Validator](https://pmc.ncbi.nlm.nih.gov/tools/stylechecker/). Currently there are still a lot of errors, so we're not done yet.

### check input

However, **before you do this**, check the input. Check the `.tex` files (these tend to be of the type `main.tex` containing a `body.tex`, sometimes with appendices and such). Also check the `.bib` files (`bibliography.bib`). These files can contain mistakes that will trip up the conversion. Run `fixbib` to clean up the bibliography.

`fixbib` is not included in the main script because it is expected that many irregularities will occur and need manual attention. It would also make debugging very difficult. So it is separate and expected to grow. (Several scripts that "check" biblatex and bibtex can be found on [Pypi](https://pypi.org/search/?q=biblatex) but none seems to do what was needed here).

For the correction of `.tex` files no script was created. Out of scope and the author's responsibility.

### bibliographies
JATS is not meant to support bibliographical style. Style support on the publication platform AUP Online is minimal. CCR's APA style is not supported. What is left is to manhandle the JATS into semi APA and be content with basic online rendering. Not worse than the PDFs produced so far, though.

Another file that is likely to grow is the biblatex binding `src/latexml/biblatex.sty.ltxml`. Not so much for bibliographical styling, but for unsupported tex tags in the articles.

### on the whole
Latex is a slippery beast, very different from XML. Authors do as they please. Expect continuous variety and surprises. Expect constant updating of the scripts. Do _not_ expect automatic conversion and a smooth workflow. Expect manual labor, the hallmark of a good editor.

### testing

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

### repository structure
- `src/latex_jats/` | Python package: main converter (`convert.py`) and bibliography cleaner (`fixbib.py`)
- `src/latexml/` | LaTeXML bindings: `ccr.cls.ltxml` and `biblatex.sty.ltxml`
- `src/lua/` | Pandoc Lua filter for metadata extraction (`ccr_latex.lua`)
- `src/css/` | Stylesheets for LaTeXML HTML preview output
- `examples/` | Reference JATS XML examples
