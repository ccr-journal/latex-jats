# JATS XML findings for AUP / Ingenta Edify

Our working reference for "what to emit, what works, what doesn't" when
producing JATS XML for the Ingenta Edify platform that AUP Online runs on.

Two sources feed this file:

1. **Paraphrased** from the Ingenta Edify "JATS XML Guidelines" PDFs
   (received 2026-04-21; kept locally outside this repo, not redistributable).
   We may rewrite and summarize but should not copy verbatim. If a constraint
   is unsourced below, assume it came from the guide.
2. **Empirical** findings from our own test articles and from direct
   correspondence with Crius (the typesetter). These are flagged with
   "*Empirical:*" and cite the article and/or date.

The spec target is **NISO JATS 1.1 Journal Publishing**. Edify accepts a
subset of JATS 1.1 — XML that validates here will validate against 1.1, but
not vice versa.

## General requirements

- Well-formed XML, valid against the JATS 1.1 DTD.
- UTF-8.
- Numeric character references (`&#…;`) are fine; reserve `&amp;`/`&lt;`/`&gt;` for literal display, not encoding tricks.
- Two accepted article shapes: fully-tagged full-text XML (preferred) or metadata-only XML for PDF-only articles.

### Issue zip packaging

- One zip per issue, delivered over SFTP.
- Zip filename and every internal filename must be alphanumeric (no spaces, no special chars).
- All articles in a zip must share the same journal-meta and issue-meta — mismatches reject the whole zip.
- File names must be unique across the zip (even across folders).
- Image / PDF files referenced from the XML must match by **bare filename with extension** — no folder prefix.

### Article wrapper

- `<article article-type="…">` — value is case-sensitive, may contain hyphens, no spaces. JATS-documented values are accepted by default; extras require publisher-admin configuration.

## Front matter

### Journal metadata

- `journal-id[@journal-id-type="publisher-id"]`, `journal-title-group/journal-title`, `issn`.
- ISSN `pub-type` differs by JATS version: `"epub"`/`"ppub"` in JATS 1.0; `"electronic"`/`"print"` in JATS 1.1+. We target 1.1.

### Issue metadata

- Required: `volume`, `issue`, `pub-date`. Used verbatim — `01` ≠ `1`. Omit volume/issue for Ahead-of-Print / Fast Track.
- Optional `issue-title` overrides the issue number in display.

### Article metadata

- Required: `article-title`, `article-id`, and either (`fpage` + `lpage`) or `elocation-id`.
- Optional: `subtitle`, `contrib-group`, `author-notes`, `self-uri`, `kwd-group`, `permissions`, `history`, `abstract`.
- Online First articles must omit volume/issue and page numbers.

### Language

Resolved in order:

1. `article-title/@xml:lang`
2. `article/@xml:lang`
3. Default `"en"`.

Always two-letter lowercase ISO codes.

### Publication dates

- At least one `pub-date` is required; empty/missing → rejection.
- `day`/`month` default to `1` if omitted, but specifying month is strongly recommended.
- Seasonal dates use `<season>` *in addition to* `<year>` (and ideally `<month>`); displayed as "Season, Year".

### Publication history

`article-meta/history/date` with `@date-type` ∈ `received`/`submitted` ("Received"), `accepted` ("Accepted"), `revised` ("Revised"), `published`/`online` ("Published online"), `corrected` ("Corrected"), `pubcorrected` ("Publisher error corrected"). One date per type.

### Self-URI (PDF link)

- Required inside `article-meta`.
- `@content-type="pdf"`, `@xlink:href` = bare PDF filename with extension, no folder prefix.
- Exactly one PDF per article. Missing target file → zip rejection.

### Article titles

- Tag as `<article-title>`.
- Optional `@xml:lang` (lowercase two-letter ISO; defaults to `en`).
- Multilingual: original in `<article-title>`, translations in `<trans-title-group>/<trans-title>` each with their own `@xml:lang`.

### Abstract

- `<abstract>` inside `article-meta`.
- `<xref>` inside `<abstract>` only resolves within the full-text tab — not from the abstract tab itself (so abstract-tab xrefs are effectively dead).
- **Not supported inside abstracts:** figures, tables, media, supplementary material, references, related content.
- **Supported:** titled `<sec>` blocks (sections with their own `<title>`).
- Multilingual: original in `<abstract xml:lang="…">`, translations in `<trans-abstract xml:lang="…">`.

### Keywords

- `<kwd-group>` with one `<kwd>` per keyword.

### Copyright

Edify picks copyright text in this priority order:

1. `permissions/license[@license-type='licensed-commercial-use']`
2. `copyright-statement` (optionally concatenated with the value of a `license[@license-type='open']` or `'free']` element if present)
3. `copyright-year` + `copyright-holder`
4. `copyright-holder` alone

### Conflict of interest

Tag as `author-notes/fn[@fn-type='COI-statement']`. Mixed content (links etc.) allowed.

### Permissions

Detailed rules live in a separate "Content Licensing XML Guidelines" doc we haven't received.

## Contributors and affiliations

- `<contrib>` exactly one `<name>` per contrib.
- **`<contrib>` with any `contrib-type` other than `"author"` is silently ignored by Edify.** Editors, translators, etc. need a different mechanism.
- Allowed children: `name/{given-names,surname,prefix,suffix}`, `email`, `role`, `xref[@ref-type="aff"]`, `xref[@ref-type="author-note"]`, `contrib-id[@contrib-id-type="orcid"]`, `aff`.
- `aff-alternatives` is **not** supported.

### Two valid affiliation styles

- **Style 1 — inline:** `<aff>` nested directly inside `<contrib>`.
- **Style 2 — sibling:** `<aff id="affN">` placed as a sibling of `<contrib>` *inside* `<contrib-group>`, linked from `<contrib>` via `<xref ref-type="aff" rid="affN"/>`.

*Empirical (URMA submission failure, see memory note `project_aup_affiliation_shape`):* Placing `<aff>` **outside** `<contrib-group>` silently drops it on the rendered site even though it validates. Both styles above work; we emit Style 2 via `collapse_affiliations` (LaTeX) and `group_affiliations` (Quarto).

The guide itself flags a caveat at the same effect: Style 2 has historically rendered inconsistently on Ingenta, and the guide author recommends Style 1 until confirmed otherwise. We've found Style 2 works as long as the `<aff>` siblings are inside `<contrib-group>`.

### Structured `<aff>` shape

Both pipelines emit structured affiliations rather than free-form text inside `<aff>`. The target shape (issue #47, ccr.cls v0.09+ / ccr-quarto structured YAML) is:

```xml
<aff id="affN">
  <institution content-type="department">Department of X</institution>   <!-- optional -->
  <institution-wrap><institution>Organisation Name</institution></institution-wrap>
  <country country="NL">NL</country>                                       <!-- optional -->
</aff>
```

- `content-type="department"` is the JATS canonical value. Pandoc's JATS writer emits `"dept"`; we normalize it to `"department"` in `group_affiliations` so both paths converge.
- `<country>` text is the ISO 3166-1 alpha-2 code (matching what Pandoc emits). The `country=` attribute carries the same code in canonical JATS form — this lets us later change the text to a full country name (e.g. "Netherlands") without losing the machine-readable code. **Open:** confirm against the Ingenta XML guide whether the bare ISO code as text renders correctly in Edify or whether the full country name should be substituted.

### ORCID

`<contrib-id contrib-id-type="orcid" authenticated="true|false">` containing the ORCID URL as text. `authenticated="true"` is what unlocks Crossref auto-update.

## Body

### Figures (`<fig>`)

- `<fig>` is required to have `@id` — XMLs without it are rejected.
- Placed *after* the citing paragraph, never inside it. Multiple figures cited from one paragraph: list in citation order.
- Title resolution order: `<label>` → `<caption>/<title>` → `<graphic>/@xlink:href` → "Untitled".
- Mandatory child: `<graphic xlink:href="…">` with a bare filename (with extension), unique across the issue, no folder prefix.
- Optional children: `<label>`, `<caption>`, `<copyright>`/`<copyright-statement>`.
- **Tables inside `<fig>` are not supported.**

*Empirical (FOOT, 2026):* `<fig>` containing `<code>` (or any non-graphic block-level content) does not render — Listing 1 in FOOT was silently dropped, which also shifted the figure thumbnail order. Authors should inline code listings rather than wrap them in a float. Crius's suggestion to use `<preformat>` instead of `<code>` doesn't address the underlying issue (the `<fig>` placement). Tracked in #44.

*Empirical (Crius 2026-04):* Subfigures should use a `<fig-group>` whose children are each a full `<fig>` (own `<label>`, `<caption>`, `<graphic>`). A `<fig-group>` containing bare `<graphic>` siblings without `<fig>` wrappers is **not** supported. Cross-references must point at the inner `<fig>` id, not the `<fig-group>` id. Layout hints (horizontal/vertical) are ignored — orient the artwork yourself. Tracked in #45.

### Inline graphics

- `<inline-graphic xlink:href="…">` — same filename rules as `<graphic>`.

*Empirical (ELDA + Crius 2026-04):* `<inline-graphic>` inside `<td>` is technically supported but Crius advises against images in table cells because rendering varies across platforms. Block-level `<graphic>` inside `<td>` is dropped entirely (the ELDA failure). Our `fix_graphic_in_td` rewrites `<graphic>` → `<inline-graphic>` and warns. Preferred alternative: lift the image into a standalone `<fig>` float and reference it from the cell. Tracked in #46.

### Tables (`<table-wrap>`)

- `<table-wrap>` requires `@id`. Placed after the citing paragraph.
- May contain `<label>` and `<caption>`.
- Two tagging styles:
  - **XHTML tables** — `<table>` inside `<table-wrap>`, using the JATS XHTML table model.
  - **Image tables** — `<graphic xlink:href="…">` inside `<table-wrap>` instead of `<table>`. Each table image is its own file.

### MathML

- Use the `mml:` namespace prefix (`<mml:math>`) to validate against the JATS DTD.
- Edify renders MathML through MathJax.
- Equations can also be supplied as images.
- A separate "MathML guidelines" doc exists but we haven't received it.

### Related articles

- `<related-article related-article-type="…" ext-link-type="doi" xlink:href="10.…">` with the target DOI as `@xlink:href` (no `doi.org/` prefix).
- `@related-article-type` must be one of the JATS-documented values.
- `<related-object>` is **not** supported.

## Back matter

- Allowed top-level children of `<back>`: `ack`, `app-group`, `bio`, `fn-group`, `ref-list`, `notes`, `sec`.

*Empirical (MULL + Crius 2026-04):* Crius themselves place `<ack>` at the end of `<body>`, **not** inside `<back>`. In our test articles, MULL (with `<ack>` directly before `<fn-group>` in `<back>`) shows no symbol numbers in the Notes list; FOOT (no `<ack>`) and URMA (with `<app-group>` before `<fn-group>`) both render correctly. Crius's working hypothesis is that the `<ack>` placement breaks `<fn-group>` numbering. Tracked in #42.

*Empirical (Crius 2026-04):* The `id` attribute on `<p>` inside `<fn>` is redundant — Crius flagged it as unnecessary; not believed to be the trigger for the MULL numbering failure but should be dropped. Tracked in #42.

### References

- **Exactly one `<ref-list>`** in `<back>`. Multiple `<ref-list>` elements are not allowed. We enforce this via `dedupe_ref_lists` (biber 2.19+ with `sortcites=true` emits multiple `\datalist` blocks; LaTeXML turns each into its own `<bibliography>`).
- Each entry is a `<ref id="…">` with a stable id — best practice is an alphanumeric prefix plus an incrementing number.
- Use `<element-citation>` or `<mixed-citation>`. `<nlm-citation>` is deprecated in JATS 1.1 and Edify strongly discourages it.
- `@publication-type` is required on the citation element.
- `<pub-id pub-id-type="doi">` / `<pub-id pub-id-type="pmid">` auto-construct Crossref / PubMed links.
- Tag at the most granular level possible (per-author names, title, source, volume, pages) — Edify uses this for Crossref / Google Scholar matching.

**`element-citation`:** No embedded punctuation. Edify supplies all punctuation and spacing itself.

**`mixed-citation`:** Punctuation and spacing inside the citation element are preserved verbatim. Edify will *not* add punctuation, so any commas/dots/colons must be present in the source.

### Footnotes

- Wrap in `<fn-group>`. One `<fn>` per footnote. `<fn>` needs `@id` if it is the target of an `<xref>`.
- Provide `<fn-group>/<title>` to customise the section heading; without it Edify inserts a default "Notes" heading.
- See the `<ack>` empirical note above — placement of `<fn-group>` matters relative to its siblings in `<back>`.

## Supplementary material

- Tagged inside `<article-meta>` as `<supplementary-material id="…" xlink:title="local_file" xlink:href="…" mimetype="…">`, with a `<caption><p>…</p></caption>` child describing the supplement.
- The guide only documents the local-file shape (`xlink:title="local_file"`, real filename in `@xlink:href`, real mimetype).

*Empirical (MULL + Crius 2026-04):* External `<supplementary-material>` links (e.g. an OSF/Zenodo URL in `@xlink:href`) **do not** appear in AUP's "Supplements" tab — that tab is only populated by files supplied directly to the typesetter. The external link is still rendered inline wherever the marker appears in body/footnote text, but the Supplements UI stays empty. Our `<supplementary-material xlink:href="https://…">` shape remains valid JATS and is useful for other publishers, so we keep emitting it; we just need to manage author expectations. Tracked in #43.

## Open items / unverified

- Whether `<preformat>` actually renders code listings better than `<code>` on AUP. Crius said "should work in principle" but had no first-hand confirmation. Largely moot if we resolve #44 by inlining code outside `<fig>`.
- Whether an Ingenta-specific RNG/DTD/Schematron exists on top of JATS Publishing 1.2. Asked Crius; no answer.
- Empirical confirmation that `<xref rid>` to an inner subfigure `<fig>` id resolves on the rendered page, and that an xref to the outer `<fig-group>` id does not. Will be answered by publishing RIGH full-text (#45).
- Empirical confirmation that `<inline-graphic>` inside `<td>` renders acceptably on AUP. Will be answered by republishing ELDA (#46).
- Content-licensing rules: separate doc from Ingenta not yet received.
- MathML rules: separate doc from Ingenta not yet received.
