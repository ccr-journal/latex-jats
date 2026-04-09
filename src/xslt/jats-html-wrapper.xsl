<?xml version="1.0" encoding="utf-8"?>
<!--
  Wrapper XSLT for the NLM JATS-to-HTML preview stylesheet.

  Imports main/jats-html.xsl and overrides specific templates to add
  title attributes that show each element's semantic role on mouseover.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:mml="http://www.w3.org/1998/Math/MathML"
    exclude-result-prefixes="mml">
  <xsl:import href="main/jats-html.xsl"/>

  <!-- Strip the mml: namespace prefix so browsers recognise MathML in HTML -->
  <xsl:template match="mml:*">
    <xsl:element name="{local-name()}">
      <xsl:copy-of select="@*"/>
      <xsl:apply-templates/>
    </xsl:element>
  </xsl:template>

  <!-- Display equations: show LaTeX source as tooltip -->
  <xsl:template match="disp-formula | statement">
    <div class="{local-name()} panel">
      <xsl:if test=".//mml:math/@alttext">
        <xsl:attribute name="title">
          <xsl:value-of select=".//mml:math/@alttext"/>
        </xsl:attribute>
      </xsl:if>
      <xsl:call-template name="named-anchor"/>
      <xsl:apply-templates select="." mode="label"/>
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <!-- Inline equations: show LaTeX source as tooltip -->
  <xsl:template match="inline-formula">
    <span class="inline-formula">
      <xsl:if test="mml:math/@alttext">
        <xsl:attribute name="title">
          <xsl:value-of select="mml:math/@alttext"/>
        </xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </span>
  </xsl:template>

  <!-- Article title -->
  <xsl:template match="title-group/article-title" mode="metadata">
    <h1 class="document-title" title="Article title">
      <xsl:apply-templates/>
      <xsl:if test="../subtitle">:</xsl:if>
    </h1>
  </xsl:template>

  <!-- Author / affiliation rows -->
  <xsl:template mode="metadata" match="article-meta/contrib-group">
    <xsl:for-each select="contrib">
      <div class="metadata two-column table">
        <div class="row">
          <div class="cell" style="text-align: right" title="Author">
            <xsl:call-template name="contrib-identify"/>
          </div>
          <div class="cell" title="Affiliation">
            <xsl:call-template name="contrib-info"/>
          </div>
        </div>
      </div>
    </xsl:for-each>
    <xsl:variable name="misc-contrib-data"
      select="*[not(self::contrib | self::xref)]"/>
    <xsl:if test="$misc-contrib-data">
      <div class="metadata two-column table">
        <div class="row">
          <div class="cell">&#160;</div>
          <div class="cell">
            <div class="metadata-group">
              <xsl:apply-templates mode="metadata"
                select="$misc-contrib-data"/>
            </div>
          </div>
        </div>
      </div>
    </xsl:if>
  </xsl:template>

  <!-- Section headings -->
  <xsl:template name="main-title"
    match="abstract/title | body/*/title |
           back/title | back[not(title)]/*/title">
    <xsl:param name="contents">
      <xsl:apply-templates/>
    </xsl:param>
    <xsl:if test="normalize-space(string($contents))">
      <h2 class="main-title" title="Section title">
        <xsl:copy-of select="$contents"/>
      </h2>
    </xsl:if>
  </xsl:template>

  <!-- Subsection headings -->
  <xsl:template name="section-title"
    match="abstract/*/title | body/*/*/title |
           back[title]/*/title | back[not(title)]/*/*/title">
    <xsl:param name="contents">
      <xsl:apply-templates/>
    </xsl:param>
    <xsl:if test="normalize-space(string($contents))">
      <h3 class="section-title" title="Subsection title">
        <xsl:copy-of select="$contents"/>
      </h3>
    </xsl:if>
  </xsl:template>

  <!-- Figures and tables -->
  <xsl:template match="boxed-text | chem-struct-wrap | fig |
                       table-wrap | chem-struct-wrapper">
    <xsl:variable name="gi">
      <xsl:choose>
        <xsl:when test="self::chem-struct-wrapper">chem-struct-wrap</xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="local-name(.)"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="tooltip">
      <xsl:choose>
        <xsl:when test="self::fig">Figure</xsl:when>
        <xsl:when test="self::table-wrap">Table</xsl:when>
        <xsl:when test="self::boxed-text">Box</xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="local-name(.)"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <div class="{$gi} panel" title="{$tooltip}">
      <xsl:if test="not(@position != 'float')">
        <xsl:attribute name="style">display: float; clear: both</xsl:attribute>
      </xsl:if>
      <xsl:call-template name="named-anchor"/>
      <xsl:apply-templates select="." mode="label"/>
      <xsl:apply-templates/>
      <xsl:apply-templates mode="footnote"
        select="self::table-wrap//fn[not(ancestor::table-wrap-foot)]"/>
    </div>
  </xsl:template>

  <!-- Fig-group, fn-group, table-wrap-foot, etc. -->
  <xsl:template match="array | disp-formula-group | fig-group |
    fn-group | license | long-desc | open-access | sig-block |
    table-wrap-foot | table-wrap-group">
    <xsl:variable name="tooltip">
      <xsl:choose>
        <xsl:when test="self::fig-group">Figure group</xsl:when>
        <xsl:when test="self::fn-group">Footnotes</xsl:when>
        <xsl:when test="self::table-wrap-foot">Table notes</xsl:when>
        <xsl:when test="self::table-wrap-group">Table group</xsl:when>
        <xsl:when test="self::disp-formula-group">Equation group</xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="local-name()"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <div class="{local-name()}" title="{$tooltip}">
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <!-- Labels (suppress those already acquired by parent via mode="label") -->
  <xsl:template match="app/label | boxed-text/label |
    chem-struct-wrap/label | chem-struct-wrapper/label |
    disp-formula/label | fig/label | fn/label | ref/label |
    statement/label | supplementary-material/label | table-wrap/label"
    priority="2">
  </xsl:template>

  <xsl:template match="label" name="label">
    <h5 class="label" title="Label">
      <xsl:apply-templates/>
    </h5>
  </xsl:template>

  <!-- Captions -->
  <xsl:template match="caption">
    <div class="caption" title="Caption">
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <!-- Footnotes in back matter -->
  <xsl:template match="fn" mode="footnote">
    <div class="footnote" title="Footnote">
      <xsl:call-template name="named-anchor"/>
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <!-- References -->
  <xsl:template match="ref/* | ref/citation-alternatives/*" priority="0">
    <p class="citation" title="Reference">
      <xsl:call-template name="named-anchor"/>
      <xsl:apply-templates/>
    </p>
  </xsl:template>

  <!-- Override for element-citation to use APA-style formatting from the
       imported main stylesheet. Without this, the priority-0 ref/* match
       above wins because wrapper templates take import precedence. -->
  <xsl:template match="ref/element-citation" priority="1">
    <xsl:apply-imports/>
  </xsl:template>

  <!-- Footnote / affiliation xrefs: render in superscript so the marker is
       distinguishable from running text. The default metadata-inline
       template wraps xrefs in [..] brackets, which is overridden here. -->
  <xsl:template match="xref[@ref-type='fn']">
    <sup><a href="#{@rid}"><xsl:apply-templates/></a></sup>
  </xsl:template>
  <xsl:template match="xref[@ref-type='aff' or @ref-type='fn']" mode="metadata-inline">
    <xsl:if test="preceding-sibling::node()[1][self::xref[@ref-type='aff' or @ref-type='fn']]">
      <sup>,</sup>
    </xsl:if>
    <sup><a href="#{@rid}"><xsl:apply-templates/></a></sup>
  </xsl:template>

  <!-- Affiliations in metadata mode: prefix with the corresponding xref
       label (e.g. "a") so the reader can match author superscripts to
       affiliations. Quarto-style id-based affiliations have no <label> child;
       we look up the matching <xref ref-type="aff"> in the front matter and
       use its text content. -->
  <xsl:template match="aff" mode="metadata">
    <xsl:variable name="aff-id" select="@id"/>
    <xsl:variable name="xref-label"
                  select="(//xref[@ref-type='aff'][@rid=$aff-id])[1]"/>
    <p class="metadata-entry">
      <xsl:call-template name="named-anchor"/>
      <xsl:if test="$xref-label">
        <strong class="aff-label">
          <xsl:value-of select="$xref-label"/>
        </strong>
        <xsl:text> </xsl:text>
      </xsl:if>
      <xsl:apply-templates/>
    </p>
  </xsl:template>

  <!-- Appendices -->
  <xsl:template match="app">
    <div class="section app" title="Appendix">
      <xsl:call-template name="named-anchor"/>
      <xsl:apply-templates select="." mode="label"/>
      <xsl:apply-templates/>
    </div>
  </xsl:template>

</xsl:stylesheet>
