import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from lxml import etree

LATEXML_DIR = Path(__file__).parent.parent / "latexml"
JATS_XSL = Path(__file__).parent.parent / "xslt" / "main" / "jats-html.xsl"


def convert_to_html(xml_file, html_file):
    """Applies the NCBI JATS preview stylesheet to produce an HTML preview."""
    transform = etree.XSLT(etree.parse(str(JATS_XSL)))
    result = transform(etree.parse(str(xml_file)))
    with open(html_file, "wb") as f:
        f.write(etree.tostring(result, pretty_print=True))


def _find_latexml_jats_xsl():
    """Find the system LaTeXML JATS XSLT file via the LaTeXML Perl module location."""
    result = subprocess.run(
        ["perl", "-e", r'use LaTeXML; use File::Basename; print dirname($INC{"LaTeXML.pm"})'],
        capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        candidate = Path(result.stdout.strip()) / "LaTeXML" / "resources" / "XSLT" / "LaTeXML-jats.xsl"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Cannot find LaTeXML-jats.xsl; is LaTeXML installed?")


# Wrapper XSLT that imports the system LaTeXML JATS stylesheet and fixes the
# ltx:personname template, which concatenates given-name tokens without spaces.
_JATS_XSLT_WRAPPER = """\
<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:ltx="http://dlmf.nist.gov/LaTeXML"
    xmlns:str="http://exslt.org/strings"
    extension-element-prefixes="str">
  <xsl:import href="{system_jats_xsl_uri}"/>
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
</xsl:stylesheet>"""


def run_latexmlc(input_tex, output_xml):
    """Runs latexmlc to convert a LaTeX file to JATS XML.

    Two-step process: first produce the LaTeXML intermediate XML, then apply a
    patched JATS XSLT (fixing the missing-spaces bug in ltx:personname).
    """
    # Note [ES]: Adding "--preload=ccr.cls",  throws an error"""
    # Note [ES]: Adding "--preload=biblatex.sty",  does not in any way change the output"""
    # WvA: but removing/renaing biblatex.sty does change the output
    import tempfile
    system_jats_xsl = _find_latexml_jats_xsl()
    wrapper_xml = _JATS_XSLT_WRAPPER.format(system_jats_xsl_uri=system_jats_xsl.as_uri())

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        command = ["latexmlc", f"--path={LATEXML_DIR}", "--destination", str(tmp_path), "--format=xml", input_tex]
        subprocess.run(command, check=True)
        transform = etree.XSLT(etree.fromstring(wrapper_xml.encode()))
        result = transform(etree.parse(str(tmp_path)))
        with open(output_xml, "wb") as f:
            f.write(etree.tostring(result, pretty_print=True))
    finally:
        tmp_path.unlink(missing_ok=True)


def fix_table_notes(jats_file):
    """Moves misplaced <p> elements inside <table-wrap> to <table-wrap-foot> and removes the original."""
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    for table_wrap in root.findall(".//table-wrap"):
        misplaced_p = table_wrap.find("p")  # find out of place <p>
        if misplaced_p is not None:
            table_wrap_foot = ET.Element("table-wrap-foot")  # create <table-wrap-foot>
            table_wrap_foot.append(misplaced_p)  # put <p> in
            table_wrap.append(table_wrap_foot)  # add<table-wrap-foot> to <table-wrap>

            table_wrap.remove(misplaced_p)  # remove out of place <p>

    tree.write(jats_file, encoding="unicode")


def clean_body(jats_file):
    """Removes empty <p> elements and misplaced <title> inside <body>."""
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    # search <body>
    body = root.find(".//body")
    if body is not None:
        # remove empty <p>
        for p in body.findall("p"):
            if not (p.text or list(p)):
                body.remove(p)

        # remove incorrect <title> in <body>
        for title in body.findall("title"):
            body.remove(title)

        # remove content between <body> and first <sec>
        # optional. you might want to wrestle it into the <front> (good luck with that)
        first_sec = body.find("sec")
        if first_sec is not None:
            comment_text = []
            for elem in list(body):
                if elem is first_sec:
                    break
                comment_text.append(ET.tostring(elem, encoding="unicode"))
                body.remove(elem)

            if comment_text:
                body.insert(0, ET.Comment("".join(comment_text)))

    tree.write(jats_file, encoding="unicode")


def fix_footnotes(jats_file):
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    # search <body>
    body = root.find(".//body")
    if body is None:
        return

    removed_fns = []  # store <fn> here

    # search all <p> in <body> for inline <fn>
    for p in body.findall(".//p"):
        # find all <fn> inside <p>
        fns = p.findall("fn")
        for fn in fns:
            # get the id
            fn_id = fn.get("id")
            # find <p> inside <fn>
            inner_p = fn.find("p")
            num = ""
            if inner_p is not None:
                inner_id = inner_p.get("id", "")
                # extract a number (e.g. "footnote1" → "1")
                m = re.search(r"footnote(\d+)", inner_id, re.IGNORECASE)
                if m:
                    num = m.group(1)
            # create <xref> and attributes
            xref = ET.Element("xref", {"rid": fn_id, "ref-type": "fn"})
            xref.text = num
            # replace <fn> with <xref>
            children = list(p)
            # remove tail
            fn.tail = ""
            removed_fns.append(fn)

            if fn in children:
                index = children.index(fn)
                p.remove(fn)
                p.insert(index, xref)
            else:
                # add if not in list
                p.append(xref)
            # removed_fns.append(fn)

    # find (or make) <back>
    back = root.find(".//back")
    if back is None:
        back = ET.Element("back")
        root.append(back)
    # find <fn-group> in <back>
    fn_group = back.find("fn-group")
    if fn_group is None:
        fn_group = ET.Element("fn-group")
        # Add <reflist> here, or at the bottom if absent
        reflist = back.find("reflist")
        if reflist is not None:
            index = list(back).index(reflist) + 1
            back.insert(index, fn_group)
        else:
            back.append(fn_group)
    # Add <fn> to <fn-group>
    for fn in removed_fns:
        fn_group.append(fn)

    tree.write(jats_file, encoding="unicode")


def fix_journal_references(jats_file):
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    # loop through all <ref>
    for ref in root.findall(".//ref"):
        mc = ref.find("mixed-citation")
        if mc is None or mc.find("volume") is None or mc.find("page-range") is None:
            continue

        # search these default elements
        person_group = mc.find("person-group")
        year_elem = mc.find("year")
        art_title = mc.find("article-title")
        page_range = mc.find("page-range")
        vol_elem = mc.find("volume")

        # remove "Cited by:" tails
        if mc.text and "Cited by:" in mc.text:
            mc.text = ""
        for child in list(mc):
            if child.tail and "Cited by:" in child.tail:
                child.tail = ""

        # extract journal name
        journal_name = None
        if art_title is not None and art_title.tail:
            m = re.search(r"\.?([A-Z][\w\s,&-]+)", art_title.tail)
            if m:
                journal_name = m.group(1).strip()
                art_title.tail = re.sub(r"\.?([A-Z][\w\s,&-]+)", "", art_title.tail).strip()
        source_elem = mc.find("source")
        if not journal_name and source_elem is not None and source_elem.text:
            journal_name = source_elem.text.strip()
            mc.remove(source_elem)

        # rebuild <mixed-citation>
        new_mc = ET.Element("mixed-citation", {"publication-type": "journal"})

        # add author
        if person_group is not None:
            new_mc.append(person_group)

        # add <year>
        if year_elem is not None:
            if len(new_mc) > 0:
                last_child = new_mc[-1]
                last_child.tail = (last_child.tail or "") + " ("
            else:
                new_mc.text = " ("
            new_mc.append(year_elem)
            year_elem.tail = "). "

        # if year_elem is not None:
        #     wrapper_year = ET.Element("dummy")
        #     wrapper_year.text = " ("
        #     new_mc.append(wrapper_year)
        #     new_mc.append(year_elem)
        #     wrapper_year2 = ET.Element("dummy")
        #     wrapper_year2.text = "). "
        #     new_mc.append(wrapper_year2)

        # add dot to article title
        if art_title is not None:
            new_mc.append(art_title)
            wrapper_title = ET.Element("dummy")
            wrapper_title.text = ". "
            new_mc.append(wrapper_title)

        # put journal name  in <source> with <italic>
        if journal_name:
            source_new = ET.Element("source")
            italic_source = ET.Element("italic")
            italic_source.text = journal_name
            source_new.append(italic_source)
            new_mc.append(source_new)
            wrapper_space = ET.Element("dummy")
            wrapper_space.text = " "
            new_mc.append(wrapper_space)

        # add volume
        if vol_elem is not None:
            new_mc.append(vol_elem)

        # add issue
        issue_num = None
        if vol_elem is not None and vol_elem.tail:
            m_issue = re.search(r"\((\d+)\)", vol_elem.tail)
            if m_issue:
                issue_num = m_issue.group(1)
                vol_elem.tail = re.sub(r"\(\d+\)", "", vol_elem.tail)
        if issue_num:
            issue_elem = ET.Element("issue")
            issue_elem.text = issue_num
            wrapper_issue = ET.Element("dummy")
            wrapper_issue.text = f" ({issue_num}), "
            new_mc.append(wrapper_issue)
        else:
            wrapper_issue = ET.Element("dummy")
            wrapper_issue.text = " "
            new_mc.append(wrapper_issue)

        # add <page-range>
        if page_range is not None:
            new_mc.append(page_range)

        # replace mc with new_mc
        mc.clear()
        for child in list(new_mc):
            mc.append(child)

    tree.write(jats_file, encoding="unicode")


# here it all comes together
def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input LaTeX file")
    parser.add_argument("output", nargs="?", help="Output JATS XML file (default: <article>/output/main.xml)")
    parser.add_argument("--html", action="store_true", help="Also generate an HTML preview via the NCBI JATS stylesheet")
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent.parent / "output" / input_path.with_suffix(".xml").name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Will convert {input_path} -> {output_path} 😎.")

    # step 1: LaTeX to JATS conversion
    print(" - Step 1: Converting LaTeX to JATS XML...")
    run_latexmlc(str(input_path), str(output_path))

    # step 2: JATS XML post processing
    print(" - Step 2: Post-processing JATS XML...")
    fix_table_notes(str(output_path))
    clean_body(str(output_path))
    fix_footnotes(str(output_path))
    # fix_journal_references(output_xml) #We can remove this; replaced with XSLT

    print(f"Saved corrected JATS XML in {output_path} 😎.")

    # step 3 (optional): generate HTML preview
    if args.html:
        html_path = output_path.with_suffix(".html")
        print(" - Step 3: Generating HTML preview...")
        convert_to_html(str(output_path), str(html_path))
        print(f"Saved HTML preview in {html_path} 😎.")


if __name__ == "__main__":
    main()
