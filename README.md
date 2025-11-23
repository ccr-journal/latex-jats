## short explanation

### overview

This is a tool to convert CCR journal articles in _latex_ format into _JATS XML_.

- it uses the [LaTeXML package](https://math.nist.gov/~BMiller/LaTeXML/) with some changes to one of its XSLTs
- it uses to additional _bindings_: one for `ccr.cls` and one for biblatex.
- it does some post-processing of the JATS output

The while thing is combined into a Python script. Run

```sh
python convert.py inputfile.tex outputfile.xml
```

We can validate the JATS file online with [J4R Validator](https://j4r.nlm.nih.gov/) or [PubMed Central Validator](https://pmc.ncbi.nlm.nih.gov/tools/stylechecker/). Currently there are still a lot of errors, so we're not done yet.

###  check input

However, **before you do this**, check the input. Check the `.tex` files (these tend to be of the type `main.tex` containing a `body.tex`, sometime with appendices and such). Also check the `.bib` files (`bibliography.bib`). These files can contain mistakes that will trip up the conversion. Run `fixbib.py` to clean up the bibliography.

`fixbib.py` is not included in the main script because it is expected that many irregularities will occur and need manual attention. It would also make debugging very difficult. So it is separate and expected to grow. (Several scripts that "check" biblatex and bibtex can be found on [Pypi](https://pypi.org/search/?q=biblatex) but none seems to do what was needed here).

For the correction of `.tex` files no script was created. Out of scope and the author's responsibility.

### bibliographies
JATS is not meant to support bibliographical style. Style support on the publication platform AUP Online is minimal. CCR's APA style is not supported. What is left is to manhandle the JATS into semi APA and be content with basic online rendering. Not worse than the PDFs produced so far, though.

This bit is done by an XSTL, `LaTeXML-jats.xsl`. This file is expected to grow as unanticipated situations in the references occur.

Another file that is likely to grow is the biblatex binding `biblatex.sty.ltxml`. Not so much for bibliographical styling, but for unsupported tex tags in the articles.

### on the whole
Latex is a slippery beast, very different from XML. Authors do as they please. Expect continuous variety and surprises. Expect constant updating of the scripts. Do _not_ expect automatic conversion and a smooth workflow. Expect manual labor, the hallmark of a good editor.

### files
- `LaTeXML-jats.xsl` | changed XSLT
- `ccr.cls.ltxml` | binding for `ccr.cls`
- `biblatex.sty.ltxml` | binding for `biblatex.sty`
- `postprocessing.py` | run the conversion script and cleans up the output
- `fixbib.py` | cleans up `bibliography.bib`
