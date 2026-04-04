<?xml version="1.0" encoding="utf-8"?>
<!--
  Wrapper XSLT for the LaTeXML JATS stylesheet.

  Imported at runtime with the system LaTeXML-jats.xsl path substituted for
  SYSTEM_JATS_XSL_URI (done in Python before writing to a temp file).
  Each template overrides a specific template from the imported stylesheet.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:ltx="http://dlmf.nist.gov/LaTeXML"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:str="http://exslt.org/strings"
    extension-element-prefixes="str">
  <xsl:import href="SYSTEM_JATS_XSL_URI"/>

  <!-- Fix: \citeyear should show only the year (e.g. "2011"), not the full author-year label.
       With structured author/year bibliography tags, CrossRef resolves the bibref to an
       ltx:ref whose text content is already just the year.  Any surrounding text nodes
       (e.g. ", p. 323" postnotes) are preserved as siblings inside the ltx:cite. -->
  <xsl:template match="ltx:cite[contains(@class,'ltx_citemacro_citeyear')]">
    <xsl:for-each select="node()">
      <xsl:choose>
        <xsl:when test="self::ltx:ref[@idref]">
          <xref rid="{@idref}">
            <xsl:variable name="full" select="normalize-space(string(.))"/>
            <xsl:choose>
              <xsl:when test="contains($full, ', ')">
                <xsl:value-of select="substring-after($full, ', ')"/>
              </xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="$full"/>
              </xsl:otherwise>
            </xsl:choose>
          </xref>
        </xsl:when>
        <xsl:when test="self::text()">
          <xsl:value-of select="."/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:apply-templates select="."/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:for-each>
  </xsl:template>

  <!-- Fix: system XSLT joins given-name tokens without separator -->
  <xsl:template match="ltx:personname">
    <name>
      <surname>
        <xsl:for-each select="str:tokenize(normalize-space(./text()),' ')">
          <xsl:if test="position()=last()"><xsl:value-of select="."/></xsl:if>
        </xsl:for-each>
      </surname>
      <given-names>
        <xsl:for-each select="str:tokenize(normalize-space(./text()),' ')">
          <xsl:if test="position()!=last()">
            <xsl:if test="position()!=1"><xsl:text> </xsl:text></xsl:if>
            <xsl:value-of select="."/>
          </xsl:if>
        </xsl:for-each>
      </given-names>
    </name>
  </xsl:template>

  <!-- Fix (18): Strip auto-generated section numbers from section titles.
       LaTeXML emits <ltx:tag close=" ">1</ltx:tag> inside <ltx:title> for numbered
       sections; the system XSLT renders it as "1 Introduction". Suppress it. -->
  <xsl:template match="ltx:section/ltx:title/ltx:tag
                      |ltx:subsection/ltx:title/ltx:tag
                      |ltx:subsubsection/ltx:title/ltx:tag"/>

  <!-- Fix (15): Use <title> inside <caption> instead of <p>.
       Also strips the <ltx:tag> child (the figure/table label like "Figure 1:")
       so that it does not appear in the caption text. -->
  <xsl:template match="ltx:caption">
    <caption>
      <title><xsl:apply-templates select="node()[not(self::ltx:tag)]"/></title>
    </caption>
  </xsl:template>

  <!-- Fix (14): Emit <label> for figures before the caption.
       LaTeXML puts the label text in <ltx:caption/ltx:tag> (e.g. "Figure 1"
       with close=": "); combine them and normalize whitespace. -->
  <xsl:template match="ltx:figure">
    <fig>
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:if test="ltx:caption/ltx:tag">
        <label><xsl:value-of select="normalize-space(concat(ltx:caption/ltx:tag, ltx:caption/ltx:tag/@close))"/></label>
      </xsl:if>
      <xsl:apply-templates select="ltx:caption"/>
      <xsl:apply-templates select="*[not(self::ltx:caption)]"/>
    </fig>
  </xsl:template>

  <!-- Fix (19): Subfigures — a parent <ltx:figure> that contains child <ltx:figure>
       elements should become a JATS <fig-group>, not a nested <fig> (which is invalid
       JATS). The predicate [ltx:figure] gives this template a higher default priority
       (0.5) than the general ltx:figure template above (0), so no explicit priority
       attribute is needed. -->
  <xsl:template match="ltx:figure[ltx:figure]">
    <fig-group>
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:if test="ltx:caption/ltx:tag">
        <label><xsl:value-of select="normalize-space(concat(ltx:caption/ltx:tag, ltx:caption/ltx:tag/@close))"/></label>
      </xsl:if>
      <xsl:apply-templates select="ltx:caption"/>
      <xsl:apply-templates select="*[not(self::ltx:caption)]"/>
    </fig-group>
  </xsl:template>

  <!-- Fix (21): LaTeXML marks first-column cells with @thead heuristically.
       LaTeX has no semantic header-column concept (l/c/r are purely alignment),
       so render all tbody cells as <td> regardless of @thead. -->
  <xsl:template match="ltx:tbody//ltx:td[@thead]">
    <td>
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:if test="@colspan">
        <xsl:attribute name="colspan"><xsl:value-of select="@colspan"/></xsl:attribute>
      </xsl:if>
      <xsl:if test="@rowspan">
        <xsl:attribute name="rowspan"><xsl:value-of select="@rowspan"/></xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </td>
  </xsl:template>

  <!-- Fix (14): Same for tables (<table-wrap>). -->
  <xsl:template match="ltx:table">
    <table-wrap>
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:if test="ltx:caption/ltx:tag">
        <label><xsl:value-of select="normalize-space(concat(ltx:caption/ltx:tag, ltx:caption/ltx:tag/@close))"/></label>
      </xsl:if>
      <xsl:apply-templates select="ltx:caption"/>
      <xsl:apply-templates select="*[not(self::ltx:caption)]"/>
    </table-wrap>
  </xsl:template>

  <!-- A floating lstlisting (lstlisting with float option) has a caption and
       is wrapped by LaTeXML in ltx:float[@class='ltx_lstlisting'].
       The default ltx:float → <boxed-text>, but <caption> is not allowed
       inside <boxed-text>. Render as <fig fig-type="listing"> instead,
       which supports <label>, <caption>, and block content. -->
  <xsl:template match="ltx:float[contains(@class,'ltx_lstlisting')]">
    <fig fig-type="listing">
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:if test="ltx:caption/ltx:tag">
        <label><xsl:value-of select="normalize-space(concat(ltx:caption/ltx:tag, ltx:caption/ltx:tag/@close))"/></label>
      </xsl:if>
      <xsl:apply-templates select="ltx:caption"/>
      <xsl:apply-templates select="*[not(self::ltx:caption) and not(self::ltx:toccaption) and not(self::ltx:tags)]"/>
    </fig>
  </xsl:template>

  <!-- lstlisting → JATS <code> block.
       The system JATS XSLT has no template for ltx:listing/ltx:listingline,
       so without this override the content is dumped as bare text. -->
  <xsl:template match="ltx:listing">
    <code>
      <xsl:apply-templates select="@xml:id" mode="copy-attribute"/>
      <xsl:apply-templates/>
    </code>
  </xsl:template>

  <xsl:template match="ltx:listingline">
    <xsl:value-of select="."/>
    <xsl:text>&#x0A;</xsl:text>
  </xsl:template>

  <!-- Fix: use @imagesrc when LaTeXML has converted the graphic to a different format
       (e.g. PDF → PNG: @imagesrc = "x1.png", a bare filename with no directory component).
       For trivial same-format copies (e.g. PNG → PNG), @imagesrc contains a temp-dir
       relative path inside the output directory; in that case fall back to @graphic,
       which is the original source-relative path that step 2c copies to the output dir. -->
  <xsl:template match="ltx:graphics">
    <xsl:variable name="href">
      <xsl:choose>
        <xsl:when test="normalize-space(@imagesrc) != '' and not(contains(@imagesrc, '/'))">
          <xsl:value-of select="@imagesrc"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="@graphic"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <graphic xlink:href="{$href}"/>
  </xsl:template>

  <!-- Fix: nested tabular inside a table cell → flatten to line-break-separated content.
       JATS does not allow <table> inside <td>/<th>. The LaTeX pattern
       \begin{tabular}[c]{@{}c@{}}line1\\line2\end{tabular} inside table cells
       is used for multi-line cell content; flatten to inline content with <break/>. -->
  <xsl:template match="ltx:tabular[ancestor::ltx:td or ancestor::ltx:th]">
    <xsl:for-each select="ltx:thead/ltx:tr | ltx:tbody/ltx:tr | ltx:tr">
      <xsl:if test="position() > 1">
        <break/>
      </xsl:if>
      <xsl:for-each select="ltx:td | ltx:th">
        <xsl:if test="position() > 1">
          <xsl:text> </xsl:text>
        </xsl:if>
        <xsl:apply-templates/>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:template>

</xsl:stylesheet>
