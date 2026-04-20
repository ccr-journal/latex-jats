# General

Note: need to check affiliations for new ccr.cls, quarto
Note: should use new latex macro for acknowledgements
Note: We don't know what the right way to encode subfigures is. RIGH and SUN have subfigures, which now emit a warning, should be tested whether they work

# URMA

https://www.aup-online.com/content/journals/10.5117/CCR2026.2.11.URMA#html_fulltext

- References don’t follow APA, and don’t show up in ‘references’ section. Hopefully fixed by changing XML
- New issue: XML renders affiliations differently -> check they still make sense
- Note: Affiliations are now nested, but in contrast to latex they are  wrapped in an institution tag, and one author has multiple affiliations. Should confirm with publisher or check after republishing

# LIND

https://www.aup-online.com/content/journals/10.5117/CCR2025.1.13.LIND#html_fulltext

- Hebrew and Arabic both display well
- Figure 1 is very strangely displayed. We upload a PNG, but the version on AUP is a gif. Solution might be that we do the conversion ourself and upload a proper JPG?
- Figure 2 is not displayed at all, shows a powerpoint link again. Problem is possibly that the graphic is in a <p> tag. Solution: strip <p> tag → Fixed by stripping p + graphic to simple p. Warns any other structure for fig tags.



# FOOT

https://www.aup-online.com/content/journals/10.5117/CCR2026.2.5.FOOT

- Listing is displayed as a “download powerpoint” stub. This fig doesn’t contain graphics, but instead contains <code> --> Solution unclear.


# ELDA

https://www.aup-online.com/content/journals/10.5117/CCR2026.1.2.ELDA

- Figures are displayed directly as SVG, which works well
- RQ! misses from “RQ1: How effectively …”This seems a problem in our XML, probably related to using labels from a bulleted list → Note: this is fixed by turning into a <def-list>, which is correct JATS, but we haven’t used it yet. Should test here (or with WEDE/MULL – or perhaps URMA but would need to alter the XML there as well since they used something like <ul><b>... instead
- Table 2 is extremely ugly due to one column being very wide, the rest too small. Looks fine in full screen. Not sure why, our XML doesn’t specify anything. Perhaps related to next problem: --> (Fix: yes, probably caused by alttext bug)
- Table 2 contains Error parsing MathML: error on line 1 at column 67: Unescaped '<' not allowed in attributes values. XML contains alttext="&lt;4" and <mml:mo mathsize="90%">&lt;</mml:mo>, maybe it needs to be escaped twice in either place.  Table C1 has same MathML errors, seemingly same cause → Solved by stripping all alttext
- Appendices are included in the full text, not in separate “Supplementen” link --> https://github.com/ccr-journal/latex-jats/issues/3
- Figures within table in Appendix A are not shown --> https://github.com/ccr-journal/latex-jats/issues/4




####

My opinion: send all four now. They all improve on the published versions (at minimum they validate under the new ccr.cls, and URMA/LIND/ELDA each have concrete fixes for previously-broken content), and bundling them with the four open questions gives Ingenta a concrete context to answer against rather than an abstract support request — which, based on the published state, has been the slower channel.

The main tradeoff: FOOT's headline issue (the listing-in-fig) isn't actually fixed in the new XML — the structure is still <fig fig-type="listing"><code>. One more resubmission won't make it render unless we also propose a concrete shape the publisher agrees to. So I'd frame FOOT's question as "here is the current JATS; what shape would you prefer — e.g., <preformat> outside <fig>, or should we pre-render the listing to an image?" — which is cheap for them to answer and gives us a path forward.

Two low-cost things worth doing before you hit send:

Open each HTML preview (<ID>.html in each convert/ dir) in a browser once. It uses our jats-preview.css, not Ingenta's renderer, but it'll catch anything visibly off on our end (like multi-aff rendering for Ana, the def-list for RQ1, MathML after alttext stripping). Five minutes total.
Confirm the four zips pass check-zip. uv run check-zip storage/manuscripts/<ID>/output/convert/<ID>.zip for each — cheap insurance that the publisher-format package is clean.
For the cover email, I'd suggest listing the four questions as a short numbered list with links to specific elements in the XMLs, e.g.:

"URMA: Ana Jovančević has two nested <aff> blocks inside her <contrib> (lines 67–78). Will that render, or do you need a specific shape for multi-affiliation authors?"
"FOOT: the YAML listing is <fig fig-type=\"listing\"><code>…</code></fig> (line 116). What structure should we use so it renders instead of becoming a download stub?"
"ELDA Appendix A: figure inside <td> via <p><graphic/></p> (GH issue #4). Should we move the figure out of the table, or is there a cell-level shape you accept?"
"Subfigures: not in this batch, but RIGH/SUN are coming. Is <fig><fig>…</fig><fig>…</fig></fig> supported, or do you need a different encoding?"
