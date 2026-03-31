# JATS Output TODO

Discrepancies between our pipeline output and the gold standard for CCR2025.1.2.YAO.
References are excluded (checked separately; only minor issues).

## Critical / Structural

- [ ] Missing XML declaration, DOCTYPE, and root `<article>` attributes (`dtd-version="1.2"`, `xml:lang="en"`, `xmlns:xsi`)
- [ ] MathML namespace prefix is `ns1:` instead of `mml:`
- [ ] Display equations rendered as `<inline-formula>` instead of `<disp-formula>`
- [ ] Text loss around footnote markers (paragraphs truncated after footnote xref in several places)
- [ ] Corrupted character in footnote 7: `¿=` instead of `>=`

## Metadata

- [ ] DOI / publisher-id missing leading zero (`CCR2025.1.2.YAO` vs gold `CCR2025.1.002.YAO`)
- [ ] ISSN `pub-type` values wrong (`print`/`electronic` vs gold `ppub`/`epub`); print ISSN should be empty
- [ ] `<pub-date>` uses `pub-type="electronic"` instead of `"epub"`; missing `<month>` element
- [ ] Missing `<lpage>` element
- [ ] Missing `<article-categories>` with `<subject>Article</subject>`
- [ ] Permissions incomplete: only `<copyright-statement>unknown</copyright-statement>`; gold has copyright-year, copyright-holder, and CC BY 4.0 license block
- [ ] Abstract missing `<title>Abstract</title>` child
- [ ] Keywords group missing `<title>Keywords:</title>` child

## Body Structure

- [ ] Figure and table elements missing `<label>` (e.g. `<label>Figure 1:</label>`)
- [ ] Captions use `<caption><p>` instead of `<caption><title>`
- [ ] Hypotheses/RQs marked up as `<list list-type="bullet">` instead of `<disp-quote>`
- [ ] Spurious `<p>.</p>` inside many `<fig>` elements
- [ ] Section title includes number (`1 Introduction` instead of `Introduction`)
- [ ] Sub-figures (Figure 3): ours nests two `<fig>` elements; gold has a single merged image

## Tables

- [ ] Table header rows: ours splits number and label into two rows; gold combines them
- [ ] Row label cells use `<th>` instead of `<td>`
- [ ] Table footnotes use `<tfoot>` rows instead of `<table-wrap-foot>/<fn-group>/<fn>` with `symbol` attributes
- [ ] Missing `<colgroup>/<col>` elements and `width` attribute on `<table>`
- [ ] Multiplication sign in "Woman x Republican" wrapped in `<inline-formula>`+MathML instead of plain `&#x00D7;`
- [ ] URLs in table cells are plain text instead of `<ext-link ext-link-type="uri">`

## IDs and Cross-references

- [ ] Section IDs differ (`s1` vs `S1`/`Sx1`)
- [ ] Figure IDs differ (`fig1` vs `S1.F1`)
- [ ] Table IDs differ (`tab1` vs `Sx4.T1`)
- [ ] Footnote IDs differ (`fn1` vs `id1`)
- [ ] Citation xref `rid` values differ (`CIT0042` vs `bib.bibx42`)
- [ ] Missing `ref-type` attribute on many figure/table/appendix xrefs
- [ ] Footnote xrefs missing `specific-use="fn"` attribute and `<sup>` wrapper
- [ ] Cross-references to appendix tables/sections lost (rendered as plain text)
- [ ] Every `<p>` has an `id` attribute; gold has none

## Back Matter

- [ ] `<fn-group>` placed after `<app-group>`; gold puts it before `<ref-list>` with `<title>Notes</title>`
- [ ] Footnotes missing `symbol` attribute
- [ ] Appendix IDs use `A1` instead of `apx1`
- [ ] Figures 4-7 inline in body; gold moves them to a separate back-matter section
- [ ] Appendix table/figure labels missing

## Citations (minor)

- [ ] Two-author citations use `et al.` instead of `&` (e.g. `Shapiro et al.` vs `Shapiro & Mahajan`)
- [ ] Citation group separator is `,` instead of `;`
