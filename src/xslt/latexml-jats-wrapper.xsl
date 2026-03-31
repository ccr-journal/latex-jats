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
    xmlns:str="http://exslt.org/strings"
    extension-element-prefixes="str">
  <xsl:import href="SYSTEM_JATS_XSL_URI"/>

  <!-- Fix: \citeyear should show only the year (e.g. "2011"), not the full author-year label.
       After CrossRef, ltx:cite[@class='ltx_citemacro_citeyear'] wraps an ltx:ref whose text
       content is the full bibitem label ("Author, Year"); we extract the part after the last ", ". -->
  <xsl:template match="ltx:cite[contains(@class,'ltx_citemacro_citeyear')]">
    <xsl:for-each select=".//ltx:ref[@idref]">
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

</xsl:stylesheet>
