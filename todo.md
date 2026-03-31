# JATS Output TODO

Discrepancies between our pipeline output and the gold standard for CCR2025.1.2.YAO.
References are excluded (checked separately; only minor issues).

## Critical / Structural

- [x] (1) Missing XML declaration, DOCTYPE, and root `<article>` attributes (`dtd-version="1.2"`, `xml:lang="en"`, `xmlns:xsi`)
- [x] (2) MathML namespace prefix is `ns1:` instead of `mml:`
- [x] (3) Display equations rendered as `<inline-formula>` instead of `<disp-formula>` — source LaTeX uses `$...$` inside `\begin{center}`, so inline is technically correct; revisit if publisher rejects
- [x] (4) Text loss around footnote markers (paragraphs truncated after footnote xref in several places) — `fn.tail` was discarded instead of transferred to the replacement `<xref>`
- [x] (5) Corrupted character in footnote 7: `¿=` instead of `>=` — LaTeXML OT1 encoding issue; added pre-conversion warning for bare `>` / `<` in text mode

## Metadata

- [x] (6) DOI / publisher-id missing leading zero (`CCR2025.1.2.YAO` vs gold `CCR2025.1.002.YAO`) — LaTeX source issue, not converter
- [x] (7) ISSN `pub-type` values wrong (`print`/`electronic` vs gold `ppub`/`epub`); print ISSN should be empty
- [x] (8) `<pub-date>` uses `pub-type="electronic"` instead of `"epub"`; ~~missing `<month>` element~~ (month deferred)
- [x] (9) Missing `<lpage>` element — emits warning when `\lastpage` not in preamble
- [x] (10) Missing `<article-categories>` with `<subject>Article</subject>`
- [x] (11) Permissions incomplete: only `<copyright-statement>unknown</copyright-statement>`; gold has copyright-year, copyright-holder, and CC BY 4.0 license block
- [x] (12) Abstract missing `<title>Abstract</title>` child
- [x] (13) Keywords group missing `<title>Keywords:</title>` child

## Body Structure

- [x] (14) Figure and table elements missing `<label>` (e.g. `<label>Figure 1:</label>`)
- [x] (15) Captions use `<caption><p>` instead of `<caption><title>`
- [x] (16) Hypotheses/RQs marked up as `<list list-type="bullet">` instead of `<disp-quote>` **Author used bullets, no fix needed**
- [x] (17) Spurious `<p>.</p>` inside many `<fig>` elements — warn only (author must remove stray period after `\includegraphics` in source)
- [x] (18) Section title includes number (`1 Introduction` instead of `Introduction`)
- [x] (19) Sub-figures (Figure 3): ours nests two `<fig>` elements; gold has a single merged image — XSLT now emits `<fig-group>` for figures containing subfigures

## Tables

- [x] (20) Table header rows: ours splits number and label into two rows; gold combines them — **don't fix, typesetter decision; LaTeX source genuinely has two rows**
- [x] (21) Row label cells use `<th>` instead of `<td>` — XSLT override for `@thead` cells in `<tbody>`
- [x] (22) Table footnotes use `<tfoot>` rows instead of `<table-wrap-foot>/<fn-group>/<fn>` with `symbol` attributes — **warn only**; author should move notes outside `\begin{tabular}` but inside `\begin{table}`
- [x] (23) Missing `<colgroup>/<col>` elements and `width` attribute on `<table>` — **skip for now**; gold widths are typesetter-invented, empty `<col>` elements serve no purpose
- [x] (24) Multiplication sign in "Woman x Republican" wrapped in `<inline-formula>`+MathML instead of plain `&#x00D7;` — **don't fix**; author wrote `$\times$`, MathML is faithful
- [x] (25) URLs in table cells are plain text instead of `<ext-link ext-link-type="uri">` — **don't fix**; no `\url{}` in source, can't reliably detect bare URLs

## IDs and Cross-references

- [x] (26) Section IDs differ (`s1` vs `S1`/`Sx1`) **don't care, don't fix**
- [x] (27) Figure IDs differ (`fig1` vs `S1.F1`) **don't care, don't fix**
- [x] (28) Table IDs differ (`tab1` vs `Sx4.T1`) **don't care, don't fix**
- [x] (29) Footnote IDs differ (`fn1` vs `id1`) **don't care, don't fix**
- [x] (30) Citation xref `rid` values differ (`CIT0042` vs `bib.bibx42`) **don't care, don't fix**
- [x] (31) Missing `ref-type` attribute on many figure/table/appendix xrefs
- [x] (32) Footnote xrefs missing `specific-use="fn"` attribute and `<sup>` wrapper
- [x] (33) Cross-references to appendix tables/sections lost (rendered as plain text) **Latex source issue, don't fix**
- [x] (34) Every `<p>` has an `id` attribute; gold has none; **don't care, don't fix**

## Back Matter

- [x] (35) `<fn-group>` placed after `<app-group>`; gold puts it before `<ref-list>` with `<title>Notes</title>`
- [x] (36) Footnotes missing `symbol` attribute
- [x] (37) Appendix IDs use `A1` instead of `apx1` **don't care, don't fix**
- [x] (38) Figures 4-7 inline in body; gold moves them to a separate back-matter section **not a bug, figures correctly placed per LaTeX source; gold placement is editorial**
- [x] (39) Appendix table/figure labels missing

## Citations (minor)

- [ ] (40) Two-author citations use `et al.` instead of `&` (e.g. `Shapiro et al.` vs `Shapiro & Mahajan`)
- [ ] (41) Citation group separator is `,` instead of `;`
