import logging
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from lxml import etree

logger = logging.getLogger(__name__)

ET.register_namespace("mml", "http://www.w3.org/1998/Math/MathML")

def _warn_bare_greater_than(tex_path):
    """Warn about bare > or < in text mode across the main .tex and \\input files.

    LaTeXML maps these to ¿ and ¡ (OT1 encoding); authors should use
    $\\ge$, $\\le$, $>$, $<$, \\textgreater, or \\textless instead.
    """
    tex_dir = tex_path.parent
    files = [tex_path]
    # collect \\input / \\include targets
    try:
        main_text = tex_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        main_text = tex_path.read_text(encoding="latin-1")
    for m in re.finditer(r'\\(?:input|include)\{([^}]+)\}', main_text):
        child = tex_dir / m.group(1)
        if not child.suffix:
            child = child.with_suffix('.tex')
        if child.exists() and child not in files:
            files.append(child)

    for fpath in files:
        try:
            lines = fpath.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = fpath.read_text(encoding="latin-1").splitlines()
        in_math_env = False
        for lineno, line in enumerate(lines, 1):
            stripped = re.sub(r'(?<!\\)%.*', '', line)  # remove comments (but not \%)
            # track math environments (simple heuristic)
            if re.search(r'\\begin\{(equation|align|math|displaymath|eqnarray)', stripped):
                in_math_env = True
            if re.search(r'\\end\{(equation|align|math|displaymath|eqnarray)', stripped):
                in_math_env = False
            if in_math_env:
                continue
            # strip inline math ($...$) before checking
            text_only = re.sub(r'\$[^$]*\$', '', stripped)
            if re.search(r'[<>]', text_only):
                logger.warning(f'bare > or < in text mode ({fpath.name}:{lineno}): '
                               f'LaTeXML will render this as ¿ or ¡. '
                               f'Use $\\ge$, $\\le$, $>$, or $<$ instead.')


LATEXML_DIR = Path(__file__).parent.parent / "latexml"
JATS_XSL = Path(__file__).parent.parent / "xslt" / "main" / "jats-html.xsl"
CSS_SRC = Path(__file__).parent.parent / "css" / "jats-preview.css"


def convert_to_html(xml_file, html_file):
    """Applies the NCBI JATS preview stylesheet to produce an HTML preview."""
    transform = etree.XSLT(etree.parse(str(JATS_XSL)))
    result = transform(etree.parse(str(xml_file)))
    with open(html_file, "wb") as f:
        f.write(etree.tostring(result, pretty_print=True))
    _move_keywords_to_front(html_file)
    _reformat_article_info_cell(html_file)
    shutil.copy2(CSS_SRC, Path(html_file).parent / "jats-preview.css")


def _move_keywords_to_front(html_file):
    """Move the keywords block from article-footer into article-front, below the abstract."""
    from lxml import html as lxml_html

    tree = lxml_html.parse(html_file)
    root = tree.getroot()

    footer = next(iter(root.xpath('//*[@id="article-footer"]')), None)
    if footer is None:
        return

    chunk_list = footer.xpath('.//div[contains(@class,"metadata-chunk")]')
    if not chunk_list:
        return
    chunk = chunk_list[0]

    kwd_texts = []
    for p in chunk.xpath('.//p[contains(@class,"metadata-entry")]'):
        spans = p.xpath('.//span[@class="generated"]')
        if spans and spans[0].tail:
            kwd_texts.append(spans[0].tail.strip())

    if not kwd_texts:
        return

    front = next(iter(root.xpath('//*[@id="article-front"]')), None)
    if front is None:
        return

    abstract_table_list = front.xpath(
        './/div[contains(@class,"two-column") and contains(@class,"table")'
        ' and .//h4[contains(@class,"callout-title")]]'
    )
    if not abstract_table_list:
        return
    abstract_table = abstract_table_list[0]

    kwd_div = lxml_html.fragment_fromstring(
        '<div class="kwd-group-inline"><span class="kwd-label">Keywords: </span>'
        + ", ".join(kwd_texts) + "</div>"
    )

    parent = abstract_table.getparent()
    idx = list(parent).index(abstract_table)
    parent.insert(idx + 1, kwd_div)

    # Remove the metadata-area containing keywords from the footer
    area_list = chunk.xpath('ancestor::div[contains(@class,"metadata-area")]')
    if area_list:
        area = area_list[-1]
        area_parent = area.getparent()
        if area_parent is not None:
            area_parent.remove(area)

    doctype = (
        b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"'
        b' "http://www.w3.org/TR/html4/loose.dtd">\n'
    )
    with open(html_file, "wb") as f:
        f.write(doctype)
        f.write(lxml_html.tostring(root, pretty_print=True))


def _reformat_article_info_cell(html_file):
    """Replace the 6-row article-info cell in the header with two compact lines:
    'CCR {vol}.{issue} ({year}) {page} – ?' and a DOI link."""
    from lxml import html as lxml_html

    tree = lxml_html.parse(html_file)
    root = tree.getroot()

    front = next(iter(root.xpath('//*[@id="article-front"]')), None)
    if front is None:
        return

    # First metadata table, second cell (article info)
    first_table = next(iter(front.xpath(
        './/div[contains(@class,"two-column") and contains(@class,"table")]'
    )), None)
    if first_table is None:
        return

    cells = first_table.xpath('.//div[contains(@class,"cell")]')
    if len(cells) < 2:
        return
    art_cell = cells[1]

    # Extract field values from p.metadata-entry spans
    fields = {}
    for p in art_cell.xpath('.//p[contains(@class,"metadata-entry")]'):
        spans = p.xpath('span')
        if not spans:
            continue
        label = spans[0].text_content().strip().rstrip(": ")
        value = (spans[0].tail or "").strip()
        fields[label] = value

    year = fields.get("Publication date (electronic)", "")
    vol = fields.get("Volume", "")
    issue = fields.get("Issue", "")
    page = fields.get("Page", "")
    doi = fields.get("DOI", "")

    mg = art_cell.find('.//div[@class="metadata-group"]')
    if mg is None:
        return
    mg.clear()

    if vol and issue and year and page:
        cite_line = lxml_html.fragment_fromstring(
            f'<p class="metadata-entry">'
            f'CCR {vol}.{issue} ({year}) {page}\u2013?'
            f'</p>'
        )
        mg.append(cite_line)

    if doi:
        doi_url = f"https://doi.org/{doi}"
        doi_line = lxml_html.fragment_fromstring(
            f'<p class="metadata-entry">'
            f'<a href="{doi_url}">{doi_url}</a>'
            f'</p>'
        )
        mg.append(doi_line)

    doctype = (
        b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"'
        b' "http://www.w3.org/TR/html4/loose.dtd">\n'
    )
    with open(html_file, "wb") as f:
        f.write(doctype)
        f.write(lxml_html.tostring(root, pretty_print=True))


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


_JATS_XSLT_WRAPPER = Path(__file__).parent.parent / "xslt" / "latexml-jats-wrapper.xsl"


def run_latexmlc(input_tex, output_xml, log_dir=None):
    """Runs latexmlc to convert a LaTeX file to JATS XML.

    Two-step process: LaTeXML intermediate XML → latexmlpost --format=jats with
    a patched JATS XSLT (fixes ltx:personname spaces; runs CrossRef internally).
    If log_dir is given, LaTeXML log files are written there instead of the cwd.
    """
    # Note [ES]: Adding "--preload=ccr.cls",  throws an error"""
    # Note [ES]: Adding "--preload=biblatex.sty",  does not in any way change the output"""
    # WvA: but removing/renaing biblatex.sty does change the output
    import tempfile
    system_jats_xsl = _find_latexml_jats_xsl()
    wrapper_xml = _JATS_XSLT_WRAPPER.read_text().replace("SYSTEM_JATS_XSL_URI", system_jats_xsl.as_uri())

    if log_dir is not None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        stem = Path(output_xml).stem
        latexml_log = Path(log_dir) / f"{stem}.latexml.log"
        post_log = Path(log_dir) / f"{stem}.latexmlpost.log"
    else:
        latexml_log = post_log = None

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp_latexml, \
         tempfile.NamedTemporaryFile(suffix=".xsl", delete=False) as tmp_xsl:
        latexml_path = Path(tmp_latexml.name)
        xsl_path = Path(tmp_xsl.name)
        tmp_xsl.write(wrapper_xml.encode())
    try:
        latexmlc_cmd = ["latexmlc", f"--path={LATEXML_DIR}", "--destination", str(latexml_path), "--format=xml", input_tex]
        if latexml_log:
            latexmlc_cmd.append(f"--log={latexml_log}")
        subprocess.run(latexmlc_cmd, check=True)

        post_cmd = ["latexmlpost", f"--stylesheet={xsl_path}", "--format=jats",
                    "--destination", str(output_xml), str(latexml_path)]
        if post_log:
            post_cmd.append(f"--log={post_log}")
        subprocess.run(post_cmd, check=True)
    finally:
        latexml_path.unlink(missing_ok=True)
        xsl_path.unlink(missing_ok=True)


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


def warn_fig_paragraphs(jats_file):
    """Warns about stray <p> elements inside <fig> that contain only punctuation/whitespace.

    These typically originate from a period placed after \\includegraphics in the LaTeX
    source (e.g. \\includegraphics{img.png}.). The stray text is preserved in the JATS
    output; the author should remove it from the source.
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    for fig in root.findall(".//fig"):
        fig_id = fig.get("id", "<unknown>")
        for p in fig.findall("p"):
            text = (p.text or "").strip()
            if text and not any(c.isalnum() for c in text):
                logging.warning(
                    f"Stray text in figure {fig_id!r}: {text!r} — "
                    "remove the trailing punctuation after \\includegraphics in the LaTeX source"
                )


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
    # LaTeXML's JATS XSLT (LaTeXML-jats.xsl) converts \footnote to inline <fn>
    # elements inside <p>, which is valid JATS. The publisher expects the other
    # valid pattern: <xref> in the body pointing to <fn> in a <fn-group> in <back>.
    # This can't be fixed in the LaTeXML bindings (they control ltx:* mapping, not
    # the JATS output), so we restructure here.
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
            xref = ET.Element("xref", {"rid": fn_id, "ref-type": "fn", "specific-use": "fn"})
            sup = ET.SubElement(xref, "sup")
            sup.text = num
            # replace <fn> with <xref>
            children = list(p)
            # transfer tail text to xref so it isn't lost
            xref.tail = fn.tail
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


def _clean_bbl_text(s):
    """Strip common LaTeX name-delimiter macros and braces from a bbl field string."""
    s = re.sub(r'\\bibrangedash', '--', s)
    s = re.sub(r'\\bibinitperiod', '.', s)
    s = re.sub(r'\\bibinitdelim\s*', ' ', s)
    s = re.sub(r'\\bibnamedelim[abcdi]\s*', ' ', s)
    s = s.replace('\\&', '&')                          # \& → &
    s = s.replace('``', '\u201c')                      # `` → "
    s = s.replace("''", '\u201d')                      # '' → "
    s = s.replace('`', '\u2018')                       # ` → '
    s = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', s)  # \cmd{arg} → arg
    s = re.sub(r'\\[a-zA-Z]+\s*', '', s)              # remaining \cmds
    # Strip braces (repeatedly to handle {{double}}):
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\{([^{}]*)\}', r'\1', s)
    return re.sub(r'\s+', ' ', s).strip()


def _parse_bbl_names(name_block):
    """Parse a biblatex \name{}{}{}{...} block into a list of author dicts."""
    authors = []
    # Each author is enclosed in an outer {{hash_info}{%\n  name_fields }}%
    for m in re.finditer(r'\{\{[^}]*\}\{%\s*(.*?)\}\}%', name_block, re.DOTALL):
        fields_text = m.group(1)
        family_m = re.search(r'\bfamily=\{((?:[^{}]|\{[^{}]*\})*)\}', fields_text)
        giveni_m = re.search(r'\bgiveni=\{((?:[^{}]|\{[^{}]*\})*)\}', fields_text)
        prefix_m = re.search(r'\bprefix=\{((?:[^{}]|\{[^{}]*\})*)\}', fields_text)
        if family_m:
            family = _clean_bbl_text(family_m.group(1))
            giveni = _clean_bbl_text(giveni_m.group(1)) if giveni_m else ''
            prefix = _clean_bbl_text(prefix_m.group(1)) if prefix_m else ''
            authors.append({'family': family, 'given': giveni, 'prefix': prefix,
                            'is_collab': not bool(giveni_m)})
    return authors


def parse_bbl(bbl_path):
    """Parse a biblatex v3.x .bbl file into an ordered list of entry dicts.

    Each dict has: key, type, authors (list of dicts with family, given, prefix,
    is_collab), and field/list values (title, journaltitle, booktitle, year,
    volume, number, pages, edition, doi, url, publisher, location, ...).
    """
    content = Path(bbl_path).read_text(encoding='utf-8')
    entries = []
    for entry_m in re.finditer(
            r'\\entry\{([^}]+)\}\{([^}]+)\}\{[^}]*\}(.*?)\\endentry',
            content, re.DOTALL):
        key, entry_type, body = entry_m.group(1), entry_m.group(2), entry_m.group(3)
        entry = {'key': key, 'type': entry_type, 'authors': []}

        # Parse \name{author/editor}{count}{}{...} blocks
        for nm in re.finditer(r'\\name\{(author|editor)\}\{\d+\}\{[^}]*\}\{(.*?)\n\s*\}',
                               body, re.DOTALL):
            role, name_block = nm.group(1), nm.group(2)
            if role == 'author':
                entry['authors'] = _parse_bbl_names(name_block)

        # Parse \field{name}{value} — supports up to 2 levels of nested braces
        for fm in re.finditer(r'\\field\{([^}]+)\}\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}', body):
            name, val = fm.group(1), fm.group(2)
            if not name.startswith('label') and name not in (
                    'sortinit', 'sortinithash', 'extradatescope', 'labeldatesource'):
                entry[name] = _clean_bbl_text(val)

        # Parse \list{name}{count}{% {value}% } — take the first value
        for lm in re.finditer(r'\\list\{([^}]+)\}\{\d+\}\{%\s*\{([^}]*)\}', body):
            name, val = lm.group(1), lm.group(2)
            entry[name] = _clean_bbl_text(val)
        # institution → publisher fallback (reports/techreports use \list{institution})
        if 'institution' in entry and 'publisher' not in entry:
            entry['publisher'] = entry['institution']

        # Parse \verb{name}\n\verb content\n\endverb
        for vm in re.finditer(r'\\verb\{([^}]+)\}\n\s*\\verb (.+?)\n\s*\\endverb', body):
            name, val = vm.group(1), vm.group(2).strip()
            entry[name] = val

        entries.append(entry)
    return entries


_XLINK_NS = 'http://www.w3.org/1999/xlink'

_PUB_TYPE = {
    'article': 'journal',
    'book': 'book', 'collection': 'book', 'mvbook': 'book',
    'inbook': 'book', 'incollection': 'book', 'inproceedings': 'confproc',
    'proceedings': 'confproc',
    'thesis': 'thesis', 'phdthesis': 'thesis', 'mastersthesis': 'thesis',
    'report': 'book', 'techreport': 'book', 'misc': 'book',
    'online': 'book', 'software': 'book',
}


def _append_text(elem, text):
    """Append text to the tail of the last child, or to elem.text if no children."""
    children = list(elem)
    if children:
        children[-1].tail = (children[-1].tail or '') + text
    else:
        elem.text = (elem.text or '') + text


def _is_elocator(page_str):
    """Return True if a page string is an electronic locator (not a numeric page)."""
    return bool(re.search(r'[a-zA-Z]', page_str))



def _add_pages(mc, pages, *, prefix='', suffix='.'):
    """Append <fpage>[–<lpage>] elements to mc from a pages string like '327--333'."""
    parts = re.split(r'--|\u2013', pages)
    fp = parts[0].strip()
    lp = parts[-1].strip() if len(parts) > 1 else ''
    if prefix:
        _append_text(mc, prefix)
    fpage = ET.SubElement(mc, 'fpage')
    fpage.text = fp
    # Only add <lpage> if it's different from fpage and not an e-locator
    if lp and lp != fp and not _is_elocator(lp):
        fpage.tail = '\u2013'
        lpage = ET.SubElement(mc, 'lpage')
        lpage.text = lp
        lpage.tail = suffix
    else:
        fpage.tail = suffix


def _build_mixed_citation(entry, warnings=None):
    """Build a structured JATS <mixed-citation> element from a parsed .bbl entry dict.

    If warnings is a list, heuristic decisions are appended to it so the user
    can verify them.
    """
    if warnings is None:
        warnings = []
    entry_type = entry['type']
    authors = entry.get('authors', [])
    is_collab = authors and authors[0].get('is_collab')

    title = entry.get('title', '')
    journaltitle = entry.get('journaltitle', '')
    booktitle = entry.get('booktitle', '')

    # Heuristic: misc/online with a journaltitle → treat as journal article
    treat_as_article = entry_type == 'article'
    if not treat_as_article and entry_type in ('misc', 'online') and journaltitle:
        treat_as_article = True
        warnings.append(
            f"bbl key {entry['key']!r}: type is {entry_type!r} but has "
            f"journaltitle; treating as journal article — please verify")

    # publication-type
    if is_collab:
        pub_type = 'collab'
    elif treat_as_article:
        pub_type = 'journal'
    else:
        pub_type = _PUB_TYPE.get(entry_type, 'book')

    mc = ET.Element('mixed-citation', {'publication-type': pub_type})

    # Authors / collab
    if is_collab:
        collab = ET.SubElement(mc, 'collab')
        collab.text = authors[0]['family']
        collab.tail = '.'
    elif authors:
        n = len(authors)
        for i, author in enumerate(authors):
            sn = ET.SubElement(mc, 'string-name')
            surname = ET.SubElement(sn, 'surname')
            surname.text = author['family']
            if author['prefix']:
                surname.text = author['prefix'] + ' ' + surname.text
            surname.tail = ', '
            given = ET.SubElement(sn, 'given-names')
            given.text = author['given']
            # separator after string-name
            if i < n - 2:
                sn.tail = ', '
            elif i == n - 2:
                sn.tail = ', \u0026 '
            # last author: no tail needed (year comes next)

    # Year
    year_val = entry.get('year')
    if year_val:
        _append_text(mc, ' (')
        year_elem = ET.SubElement(mc, 'year')
        year_elem.text = year_val
        year_elem.tail = '). '

    if treat_as_article:
        # Article title
        if title:
            at = ET.SubElement(mc, 'article-title')
            at.text = title
            at.tail = '. '
        # Journal source
        if journaltitle:
            src = ET.SubElement(mc, 'source')
            italic = ET.SubElement(src, 'italic')
            italic.text = journaltitle
            src.tail = ', '
        # Volume and issue
        volume = entry.get('volume', '')
        number = entry.get('number', '')
        if volume:
            vol = ET.SubElement(mc, 'volume')
            vol.text = volume
            if number:
                vol.tail = '('
                iss = ET.SubElement(mc, 'issue')
                iss.text = number
                iss.tail = '), '
            else:
                vol.tail = ', '
        # Pages
        pages = entry.get('pages', '')
        if pages:
            _add_pages(mc, pages)

    elif entry_type in ('inbook', 'incollection'):
        # Chapter title
        if title:
            ct = ET.SubElement(mc, 'chapter-title')
            ct.text = title
            ct.tail = '. '
        # Book source
        if booktitle:
            _append_text(mc, 'In ')
            src = ET.SubElement(mc, 'source')
            italic = ET.SubElement(src, 'italic')
            italic.text = booktitle
            src.tail = ' '
        # Pages
        pages = entry.get('pages', '')
        if pages:
            _add_pages(mc, pages, prefix='(pp. ', suffix='). ')

    elif is_collab:
        # Collab entries: title in <article-title> (not <source>)
        if title:
            at = ET.SubElement(mc, 'article-title')
            at.text = title
            at.tail = '. '

    else:
        # Book/misc/report: title in <source>
        if title:
            src = ET.SubElement(mc, 'source')
            italic = ET.SubElement(src, 'italic')
            italic.text = title
            # edition
            edition = entry.get('edition', '')
            if edition:
                ed_text = re.sub(r'\s*edition\s*$', '', edition, flags=re.IGNORECASE).strip()
                src.tail = ' ('
                ed = ET.SubElement(mc, 'edition')
                ed.text = ed_text
                ed.tail = '). '
            else:
                src.tail = '. '

    # Publisher (skip for journal articles and collab entries)
    publisher = entry.get('publisher', '') if not treat_as_article and not is_collab else ''
    location = entry.get('location', '') if not treat_as_article and not is_collab else ''
    if publisher:
        pub = ET.SubElement(mc, 'publisher-name')
        pub.text = publisher
        if location:
            pub.tail = ', '
            loc = ET.SubElement(mc, 'publisher-loc')
            loc.text = location
            loc.tail = '.'
        else:
            pub.tail = '.'

    # "Retrieved <month> <day>, <year>, from" — only when no DOI (URL is the
    # primary access path, not a supplement to a DOI-based reference)
    doi = entry.get('doi', '')
    urlmonth = entry.get('urlmonth', '')
    urlday = entry.get('urlday', '')
    urlyear = entry.get('urlyear', '')
    if (urlmonth or urlday or urlyear) and not doi:
        _append_text(mc, ' Retrieved ')
        _MONTH_NAMES = {
            '1': 'January', '2': 'February', '3': 'March', '4': 'April',
            '5': 'May', '6': 'June', '7': 'July', '8': 'August',
            '9': 'September', '10': 'October', '11': 'November', '12': 'December',
        }
        if urlmonth:
            m_elem = ET.SubElement(mc, 'month')
            m_elem.text = _MONTH_NAMES.get(urlmonth, urlmonth)
            m_elem.tail = ' '
        if urlday:
            d_elem = ET.SubElement(mc, 'day')
            d_elem.text = urlday
            d_elem.tail = ', '
        if urlyear:
            y_elem = ET.SubElement(mc, 'year')
            y_elem.text = urlyear
            y_elem.tail = ', from '

    # DOI or URL
    url = entry.get('url', '')
    if doi:
        _append_text(mc, ' ')
        href = f'https://doi.org/{doi}'
        link = ET.SubElement(mc, 'ext-link',
                             {'ext-link-type': 'doi',
                              '{%s}href' % _XLINK_NS: href})
        link.text = href
    elif url and not url.startswith('https://doi.org/'):
        _append_text(mc, ' ')
        link = ET.SubElement(mc, 'ext-link',
                             {'ext-link-type': 'uri',
                              '{%s}href' % _XLINK_NS: url})
        link.text = url

    return mc


def fix_references(jats_file, bbl_file):
    """Rewrites <mixed-citation> elements with structured JATS from the .bbl source data.

    Uses positional matching: .bbl entry order == JATS <ref> order (both sorted by biber).
    Includes a sanity check comparing the first author's family name against the flat text.
    """
    ET.register_namespace('xlink', _XLINK_NS)
    entries = parse_bbl(bbl_file)
    tree = ET.parse(jats_file)
    root = tree.getroot()
    refs = root.findall('.//ref')
    if len(refs) != len(entries):
        logger.warning(f'{len(refs)} refs in JATS but {len(entries)} entries in .bbl; '
                       'some may be skipped')
    for ref, entry in zip(refs, entries):
        mc = ref.find('mixed-citation')
        if mc is None:
            continue
        # Sanity check: first author family name should appear in the flat text
        flat_text = ''.join(mc.itertext())
        authors = entry.get('authors', [])
        first_family = authors[0]['family'] if authors else ''
        if first_family and first_family not in flat_text:
            logger.warning(f"bbl key {entry['key']!r}: "
                          f"family name {first_family!r} not in ref text; skipping")
            continue
        ref_warnings = []
        new_mc = _build_mixed_citation(entry, warnings=ref_warnings)
        for w in ref_warnings:
            logger.info(w)
        attrib = dict(mc.attrib)
        mc.clear()
        mc.attrib.update(attrib)
        mc.attrib.update(new_mc.attrib)
        mc.text = new_mc.text
        for child in new_mc:
            mc.append(child)
    tree.write(jats_file, encoding='unicode', xml_declaration=False)


_JOURNAL_META_XML = """\
<journal-meta>
  <journal-id journal-id-type="publisher-id">CCR</journal-id>
  <journal-title-group>
    <journal-title>Computational Communication Research</journal-title>
  </journal-title-group>
  <issn pub-type="ppub"/>
  <issn pub-type="epub">2665-9085</issn>
  <publisher>
    <publisher-name>Amsterdam University Press</publisher-name>
    <publisher-loc>Amsterdam</publisher-loc>
  </publisher>
</journal-meta>"""


def fix_citation_ref_types(jats_file):
    """Add ref-type="bibr" to xref elements that point to bibliography ref entries.

    latexmlpost converts ltx:bibref → ltx:ref before the JATS XSLT runs, so the
    XSLT's ltx:bibref template (which adds ref-type="bibr") never fires.  We restore
    the attribute here by checking whether the xref's rid matches a <ref> in <ref-list>.
    """
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()
    ref_ids = {ref.get("id") for ref in root.findall(".//ref-list//ref") if ref.get("id")}
    for xref in root.findall(".//xref"):
        if not xref.get("ref-type") and xref.get("rid") in ref_ids:
            xref.set("ref-type", "bibr")
    tree.write(jats_file, encoding="unicode")


def fix_xref_ref_types(jats_file):
    """Add ref-type to xref elements pointing to figures, tables, and sections.

    The system LaTeXML JATS XSLT does not set ref-type for structural xrefs.
    We resolve it here by checking each xref's rid against the IDs of fig,
    table-wrap, sec, and app elements in the document.
    """
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    fig_ids   = {e.get("id") for e in root.findall(".//fig")        if e.get("id")}
    table_ids = {e.get("id") for e in root.findall(".//table-wrap") if e.get("id")}
    sec_ids   = {e.get("id") for e in root.findall(".//sec")        if e.get("id")}
    app_ids   = {e.get("id") for e in root.findall(".//app")        if e.get("id")}

    for xref in root.findall(".//xref"):
        if xref.get("ref-type"):
            continue
        rid = xref.get("rid")
        if not rid:
            continue
        if rid in fig_ids:
            xref.set("ref-type", "fig")
        elif rid in table_ids:
            xref.set("ref-type", "table")
        elif rid in app_ids or rid in sec_ids:
            xref.set("ref-type", "sec")

    tree.write(jats_file, encoding="unicode")


def fix_metadata(jats_file, tex_file):
    """Replaces journal-meta with a constant CCR block and injects article metadata
    (doi, publisher-id, volume, issue, fpage, pub-date) extracted from the LaTeX preamble."""
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    # --- journal-meta: replace entirely with constant block ---
    front = root.find(".//front")
    if front is not None:
        old_jm = front.find("journal-meta")
        new_jm = ET.fromstring(_JOURNAL_META_XML)
        if old_jm is not None:
            idx = list(front).index(old_jm)
            front.remove(old_jm)
            front.insert(idx, new_jm)
        else:
            front.insert(0, new_jm)

    # --- article-meta: parse preamble and inject fields ---
    preamble = Path(tex_file).read_text(encoding="utf-8").split(r"\begin{document}")[0]

    def _get(name):
        m = re.search(r'\\' + name + r'\{([^}]*)\}', preamble)
        return m.group(1).strip() if m else None

    doi_val      = _get("doi")
    volume_val   = _get("volume")
    pubnumber_val = _get("pubnumber")
    pubyear_val  = _get("pubyear")
    firstpage_val = _get("firstpage")

    am = root.find(".//article-meta")
    if am is None:
        tree.write(jats_file, encoding="unicode")
        return

    # Replace old <article-id> placeholder with two typed elements
    for old_id in am.findall("article-id"):
        am.remove(old_id)

    insert_pos = 0
    if doi_val:
        pub_id = doi_val.split("/", 1)[1] if "/" in doi_val else doi_val
        elem_pubid = ET.Element("article-id", {"pub-id-type": "publisher-id"})
        elem_pubid.text = pub_id
        elem_doi = ET.Element("article-id", {"pub-id-type": "doi"})
        elem_doi.text = doi_val
        am.insert(insert_pos, elem_doi)
        am.insert(insert_pos, elem_pubid)
        insert_pos += 2

    # (10) Insert <article-categories> after article-id elements
    art_cat = ET.fromstring(
        '<article-categories><subj-group subj-group-type="heading">'
        '<subject>Article</subject></subj-group></article-categories>'
    )
    am.insert(insert_pos, art_cat)

    # Find insertion point: just before <permissions>
    children = list(am)
    perm_idx = next((i for i, e in enumerate(children) if e.tag == "permissions"), len(children))

    new_elems = []
    if pubyear_val:
        pub_date = ET.Element("pub-date", {"pub-type": "epub"})
        year_elem = ET.SubElement(pub_date, "year")
        year_elem.text = pubyear_val
        new_elems.append(pub_date)
    if volume_val:
        vol = ET.Element("volume")
        vol.text = volume_val
        new_elems.append(vol)
    if pubnumber_val:
        issue = ET.Element("issue")
        issue.text = pubnumber_val
        new_elems.append(issue)
    if firstpage_val:
        fpage = ET.Element("fpage")
        fpage.text = firstpage_val
        new_elems.append(fpage)
    lastpage_val = _get("lastpage")
    if lastpage_val:
        lpage = ET.Element("lpage")
        lpage.text = lastpage_val
        new_elems.append(lpage)
    else:
        logger.warning("No \\lastpage in LaTeX preamble; <lpage> will be missing from JATS output")

    for i, elem in enumerate(new_elems):
        am.insert(perm_idx + i, elem)

    # (11) Replace permissions with full copyright + CC BY 4.0 license block
    old_perm = am.find("permissions")
    if old_perm is not None:
        perm_idx_now = list(am).index(old_perm)
        am.remove(old_perm)
        copyright_year = pubyear_val or "unknown"
        perm_xml = (
            '<permissions>'
            '<copyright-statement>\u00a9 The authors</copyright-statement>'
            f'<copyright-year>{copyright_year}</copyright-year>'
            '<copyright-holder>The authors</copyright-holder>'
            '<license license-type="open-access">'
            '<license-p>This is an open access article distributed under the CC BY 4.0 license '
            '<ext-link xmlns:xlink="http://www.w3.org/1999/xlink" ext-link-type="uri" '
            'xlink:href="https://creativecommons.org/licenses/by/4.0/">'
            'https://creativecommons.org/licenses/by/4.0/</ext-link></license-p>'
            '</license>'
            '</permissions>'
        )
        am.insert(perm_idx_now, ET.fromstring(perm_xml))

    # (12) Add <title>Abstract</title> to <abstract> if missing
    abstract = root.find(".//abstract")
    if abstract is not None and abstract.find("title") is None:
        title_elem = ET.Element("title")
        title_elem.text = "Abstract"
        abstract.insert(0, title_elem)

    # (13) Add <title>Keywords:</title> to <kwd-group> if missing
    kwd_group = root.find(".//kwd-group")
    if kwd_group is not None and kwd_group.find("title") is None:
        title_elem = ET.Element("title")
        title_elem.text = "Keywords:"
        kwd_group.insert(0, title_elem)

    for kwd in root.findall(".//kwd"):
        if kwd.text:
            kwd.text = kwd.text.strip()

    tree.write(jats_file, encoding="unicode")


_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n'
_DOCTYPE = (
    '<!DOCTYPE article PUBLIC '
    '"-//NLM//DTD JATS (NISO Z39.96-2019) Journal Publishing DTD v1.2 20190208//EN" '
    '"https://jats.nlm.nih.gov/publishing/1.2/JATS-journalpublishing1-mathml3.dtd">\n'
)
_ROOT_ATTRS = {
    "dtd-version": "1.2",
    "xml:lang": "en",
    "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def finalize_xml(jats_file):
    """Add XML declaration, DOCTYPE, and required root <article> attributes."""
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    for attr, value in _ROOT_ATTRS.items():
        if attr not in root.attrib:
            root.set(attr, value)

    xml_body = ET.tostring(root, encoding="unicode")
    with open(jats_file, "w", encoding="utf-8") as f:
        f.write(_XML_DECL)
        f.write(_DOCTYPE)
        f.write(xml_body)


# here it all comes together
def main():
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input LaTeX file")
    parser.add_argument("output", nargs="?", help="Output JATS XML file (default: <article>/output/<doi-suffix>.xml)")
    parser.add_argument("--html", action="store_true", help="Also generate an HTML preview via the NCBI JATS stylesheet")
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        preamble = input_path.read_text(encoding="utf-8").split(r"\begin{document}")[0]
        m = re.search(r'\\doi\{([^}]*)\}', preamble)
        doi_suffix = m.group(1).split("/", 1)[1] if m and "/" in m.group(1) else input_path.stem
        output_path = input_path.parent.parent / "output" / f"{doi_suffix}.xml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir = output_path.parent / "logs"

    logger.info(f"Will convert {input_path} -> {output_path}")

    # step 0: warn about known LaTeX pitfalls
    _warn_bare_greater_than(input_path)

    # step 1: LaTeX to JATS conversion
    logger.info("Step 1: Converting LaTeX to JATS XML...")
    run_latexmlc(str(input_path), str(output_path), log_dir=log_dir)

    # step 2: JATS XML post processing
    logger.info("Step 2: Post-processing JATS XML...")
    fix_citation_ref_types(str(output_path))
    fix_metadata(str(output_path), str(input_path))
    fix_table_notes(str(output_path))
    warn_fig_paragraphs(str(output_path))
    clean_body(str(output_path))
    fix_footnotes(str(output_path))
    fix_xref_ref_types(str(output_path))
    # fix_journal_references(output_xml) #We can remove this; replaced with XSLT
    bbl_file = input_path.with_suffix('.bbl')
    if bbl_file.exists():
        fix_references(str(output_path), str(bbl_file))
    else:
        logger.warning(f'no .bbl file at {bbl_file}; references will be plain text')
    finalize_xml(str(output_path))

    logger.info(f"Saved corrected JATS XML in {output_path}")

    # step 2b: copy graphics from the latex source directory to the output directory
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".tif", ".tiff"}
    latex_dir = input_path.parent
    copied = []
    for img in latex_dir.iterdir():
        if img.suffix.lower() in image_exts:
            dest = output_path.parent / img.name
            if not dest.exists() or img.stat().st_mtime > dest.stat().st_mtime:
                shutil.copy2(img, dest)
                copied.append(img.name)
    if copied:
        logger.info(f"Copied {len(copied)} image(s) to output: {', '.join(copied)}")

    # step 3 (optional): generate HTML preview
    if args.html:
        html_path = output_path.with_suffix(".html")
        logger.info("Step 3: Generating HTML preview...")
        convert_to_html(str(output_path), str(html_path))
        logger.info(f"Saved HTML preview in {html_path}")
        _write_netlify_files(output_path.parent, output_path.stem)


def _write_netlify_files(output_dir, stem):
    """Write Netlify _headers and _redirects files to the output directory."""
    headers = (
        f"/{stem}.xml\n"
        f"  Content-Type: application/xml\n"
        f"  X-Content-Type-Options: nosniff\n"
    )
    redirects = f"/    /{stem}.html    301!\n"
    (output_dir / "_headers").write_text(headers)
    (output_dir / "_redirects").write_text(redirects)


if __name__ == "__main__":
    main()
