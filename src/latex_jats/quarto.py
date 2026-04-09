"""Quarto → JATS conversion pipeline.

Mirrors the LaTeX pipeline in convert.py but operates on .qmd input by
delegating the heavy lifting to ``quarto render --to jats_publishing``
and then post-processing the resulting XML to match the publisher-ready
shape produced by the LaTeX pipeline.

Reuses figure rename, pdf→svg conversion, ext-link normalization,
finalize_xml, and convert_to_html from convert.py unchanged.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from latex_jats.convert import (
    _convert_pdf_figures,
    apply_article_meta,
    apply_journal_meta,
    convert_to_html,
    finalize_xml,
    fix_ext_links,
    fix_pdf_graphic_refs,
    rename_graphics,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace + render
# ---------------------------------------------------------------------------


def prepare_quarto_workspace(example_dir: Path, workspace_dir: Path) -> bool:
    """Copy a Quarto example into the workspace.

    Mirrors prepare_workspace() for LaTeX but without LaTeX-specific validation.
    Always recreates the workspace from scratch so a stale render does not leak
    into the new run.
    """
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example_dir, workspace_dir)
    logger.info("Prepared Quarto workspace at %s", workspace_dir)
    return True


def find_qmd(directory: Path) -> Path | None:
    """Return the first .qmd file in *directory*, or None."""
    qmds = sorted(directory.glob("*.qmd"))
    return qmds[0] if qmds else None


def render_quarto(workspace_qmd: Path, log_dir: Path) -> Path:
    """Run ``quarto render`` on the qmd file inside its workspace.

    Returns the path to the produced .xml file (next to the .qmd in the
    workspace). Raises CalledProcessError on render failure.
    """
    if not shutil.which("quarto"):
        raise RuntimeError("quarto not installed or not on PATH")

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "quarto-render.log"

    workspace_dir = workspace_qmd.parent
    cmd = ["quarto", "render", workspace_qmd.name, "--to", "jats_publishing"]
    logger.info("Running: %s (cwd=%s)", " ".join(cmd), workspace_dir)

    result = subprocess.run(
        cmd,
        cwd=workspace_dir,
        capture_output=True,
        text=True,
    )
    log_file.write_text(
        f"$ {' '.join(cmd)}\n\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )
    if result.returncode != 0:
        logger.error("quarto render failed; see %s", log_file)
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

    rendered_xml = workspace_qmd.with_suffix(".xml")
    if not rendered_xml.exists():
        raise FileNotFoundError(f"quarto render produced no XML at {rendered_xml}")
    return rendered_xml


# ---------------------------------------------------------------------------
# YAML front-matter parsing
# ---------------------------------------------------------------------------


def parse_qmd_frontmatter(qmd_file: Path) -> dict:
    """Return the YAML front matter of a .qmd file as a dict.

    Uses PyYAML if available; falls back to a tiny line-based parser that
    handles the simple top-level scalar keys we care about (doi, volume,
    pubnumber, pubyear, firstpage, lastpage, title, etc.).
    """
    text = qmd_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    # Strip the first --- and find the closing ---
    body = text[3:]
    end = body.find("\n---")
    if end < 0:
        return {}
    yaml_text = body[:end]

    try:
        import yaml  # type: ignore
        data = yaml.safe_load(yaml_text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        pass

    # Minimal fallback: top-level "key: value" lines only.
    data: dict = {}
    for line in yaml_text.splitlines():
        m = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        if val == "":
            continue
        data[key] = val
    return data


def get_doi_suffix_from_qmd(qmd_file: Path) -> str:
    """Extract the DOI suffix (e.g. 'CCR2026.2.11.URMA') from the qmd YAML.

    Falls back to the file stem if no doi key is present.
    """
    meta = parse_qmd_frontmatter(qmd_file)
    doi = meta.get("doi")
    if not doi:
        logger.warning("No 'doi' in qmd front matter; using filename")
        return qmd_file.stem
    if "/" in doi:
        return doi.rsplit("/", 1)[1]
    return doi


# ---------------------------------------------------------------------------
# Post-processing fixups
# ---------------------------------------------------------------------------


def inject_metadata_from_yaml(jats_file: str, qmd_file: str) -> None:
    """Inject CCR journal-meta + article-meta built from the .qmd YAML keys."""
    meta = parse_qmd_frontmatter(Path(qmd_file))

    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    tree = ET.parse(jats_file)
    root = tree.getroot()

    apply_journal_meta(root)
    apply_article_meta(
        root,
        doi=meta.get("doi"),
        volume=meta.get("volume"),
        issue=meta.get("pubnumber"),
        pubyear=meta.get("pubyear"),
        firstpage=meta.get("firstpage"),
        lastpage=meta.get("lastpage"),
    )

    tree.write(jats_file, encoding="unicode")


def fix_empty_history(jats_file: str) -> None:
    """Drop the empty <history/> Quarto emits (causes a JATS validation error)."""
    tree = ET.parse(jats_file)
    root = tree.getroot()
    changed = False
    for parent in root.iter():
        for hist in list(parent.findall("history")):
            if len(hist) == 0 and not (hist.text and hist.text.strip()):
                parent.remove(hist)
                changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


def fix_corresp_xref(jats_file: str) -> None:
    """Lift <xref ref-type="fn"> elements out of <string-name>.

    Quarto emits the corresponding-author footnote marker inside the
    <string-name>, which JATS forbids. Move the xref to be a sibling of
    string-name (inside the contrib).
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    changed = False
    for contrib in root.findall(".//contrib"):
        for string_name in contrib.findall("string-name"):
            for xref in list(string_name.findall("xref")):
                # Capture trailing text from the xref so it isn't lost
                tail = xref.tail
                xref.tail = None
                string_name.remove(xref)
                # Append the xref as a sibling under contrib
                contrib.append(xref)
                if tail and tail.strip():
                    # Stash leftover text on the previous element of contrib
                    xref.tail = tail
                changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


def unwrap_table_fig(jats_file: str) -> None:
    """Replace ``<fig id="tbl-*"><table-wrap>...</table-wrap></fig>`` with the
    bare ``<table-wrap>``, lifting the id over.

    Warns when a tbl-* fig has no inner <table-wrap> — that indicates an
    unrendered knitr/R chunk the author needs to fix.
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    changed = False
    # Build parent map so we can splice replacements in place
    parent_map = {child: parent for parent in root.iter() for child in parent}

    for fig in list(root.iter("fig")):
        fig_id = fig.get("id") or ""
        if not fig_id.startswith("tbl"):
            continue
        inner_tw = fig.find("table-wrap")
        if inner_tw is None:
            logger.warning(
                "Empty table placeholder <fig id=%r> in Quarto output — "
                "the table chunk did not render. Author should fix the .qmd source.",
                fig_id,
            )
            continue
        # Lift id from fig onto the table-wrap if it does not already have one
        if not inner_tw.get("id"):
            inner_tw.set("id", fig_id)
        # Migrate the fig's caption into the table-wrap if the table-wrap
        # doesn't already have one (Quarto puts the caption on the outer
        # <fig> wrapper instead of the inner <table-wrap>).
        fig_caption = fig.find("caption")
        if fig_caption is not None and inner_tw.find("caption") is None:
            inner_tw.insert(0, fig_caption)
        # Migrate any stray <p> elements (e.g. add_footnote() output) from
        # the <fig> into a <table-wrap-foot> on the <table-wrap>.
        stray_ps = [p for p in fig.findall("p")]
        if stray_ps:
            tw_foot = inner_tw.find("table-wrap-foot")
            if tw_foot is None:
                tw_foot = ET.SubElement(inner_tw, "table-wrap-foot")
            for p in stray_ps:
                tw_foot.append(p)
        parent = parent_map.get(fig)
        if parent is None:
            continue
        idx = list(parent).index(fig)
        parent.remove(fig)
        parent.insert(idx, inner_tw)
        # Preserve the fig's tail whitespace on the new element
        inner_tw.tail = fig.tail
        changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


_LABEL_PREFIX_RE = re.compile(r'^\s*((?:Figure|Table)\s+[A-Za-z0-9]+[:.])\s*')


def add_fig_table_labels(jats_file: str) -> None:
    """Lift inline 'Figure N:' / 'Table N:' caption prefixes into a <label> element.

    Quarto inlines the label as caption text. The LaTeX pipeline produces
    a separate <label> element, which the publisher and our HTML XSLT expect.
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    changed = False
    for elem in root.iter():
        if elem.tag not in ("fig", "table-wrap"):
            continue
        if elem.find("label") is not None:
            continue
        caption = elem.find("caption")
        if caption is None:
            continue
        # The label text usually lives in the first <p> child or directly in caption.text
        target = caption.find("p")
        text_attr = "text"
        if target is None:
            target = caption
        first_text = (target.text or "")
        m = _LABEL_PREFIX_RE.match(first_text)
        if not m:
            continue
        label_text = m.group(1)
        new_first_text = first_text[m.end():]
        target.text = new_first_text
        label_elem = ET.Element("label")
        label_elem.text = label_text
        # Insert <label> as the first child of the fig/table-wrap
        elem.insert(0, label_elem)
        changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


def drop_orphan_fns(jats_file: str) -> None:
    """Remove <fn> elements that no <xref> points to and renumber the rest.

    Quarto duplicates inline author footnotes (e.g. a corresponding-author
    note attached to a name with ^[...]) once per surrounding author entry,
    producing several identical ``<fn id="fn1">``..``<fn id="fnN">`` blocks
    where only the last id is actually referenced. This drops the unused
    duplicates so the reader sees the footnote once, then renumbers the
    surviving labels so they start at 1 in document order (otherwise the
    surviving footnote keeps its skipped Quarto id, e.g. "4").
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    referenced = {x.get("rid") for x in root.iter("xref") if x.get("rid")}
    changed = False
    for fn_group in root.iter("fn-group"):
        for fn in list(fn_group.findall("fn")):
            fn_id = fn.get("id")
            if fn_id and fn_id not in referenced:
                fn_group.remove(fn)
                changed = True
                logger.info("Dropped orphan footnote %s (no xref points to it)", fn_id)

    # Renumber surviving footnotes so labels run 1..N in document order.
    # ids stay stable (xref rids must continue to resolve); only <label>
    # text is rewritten.
    surviving = list(root.iter("fn"))
    for new_num, fn in enumerate(surviving, start=1):
        label = fn.find("label")
        if label is not None:
            new_text = str(new_num)
            if label.text != new_text:
                label.text = new_text
                changed = True
    # Also update the visible text on each <xref ref-type="fn"> to match.
    fn_id_to_num = {fn.get("id"): str(i) for i, fn in enumerate(surviving, start=1)}
    for xref in root.iter("xref"):
        if xref.get("ref-type") != "fn":
            continue
        rid = xref.get("rid")
        if rid in fn_id_to_num:
            new_text = fn_id_to_num[rid]
            if xref.text != new_text:
                xref.text = new_text
                changed = True
            # If wrapped in <sup>, update its tail/text too — but Quarto's
            # markup uses bare xref text, so this is usually enough.

    if changed:
        tree.write(jats_file, encoding="unicode")


def move_fn_group_to_back(jats_file: str) -> None:
    """Move <fn-group> from the end of <body> into <back>."""
    tree = ET.parse(jats_file)
    root = tree.getroot()
    body = root.find(".//body")
    if body is None:
        return
    fn_groups = [fg for fg in body.findall(".//fn-group")]
    # Only move top-level fn-groups (i.e. direct children of body or sec-children of body)
    # so we don't accidentally rip footnotes out of table-wrap-foot etc.
    movable = [fg for fg in fn_groups if fg in list(body)]
    if not movable:
        return
    back = root.find("back")
    if back is None:
        back = ET.SubElement(root, "back")
    for fg in movable:
        body.remove(fg)
        back.append(fg)
    tree.write(jats_file, encoding="unicode")


def drop_empty_refs_section(jats_file: str) -> None:
    """Remove an empty ``<sec id="references">`` from <body> when a real
    ``<ref-list>`` already exists in <back>.
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    body = root.find(".//body")
    back = root.find("back")
    if body is None or back is None:
        return
    if back.find(".//ref-list") is None:
        return
    changed = False
    parent_map = {child: parent for parent in body.iter() for child in body.iter()}
    # Simpler: just look at direct children of body
    for sec in list(body.findall("sec")):
        if sec.get("id") != "references":
            continue
        # Empty if it has no children other than <title> and empty <p>
        meaningful = [c for c in sec if c.tag not in ("title",) and not (c.tag == "p" and not (c.text and c.text.strip()) and len(c) == 0)]
        if meaningful:
            continue
        body.remove(sec)
        changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


def clean_element_citations(jats_file: str) -> None:
    """Strip noisy <date-in-citation content-type="access-date"> elements that
    Quarto adds to every reference.
    """
    tree = ET.parse(jats_file)
    root = tree.getroot()
    changed = False
    for cit in root.findall(".//element-citation"):
        for d in list(cit.findall("date-in-citation")):
            if d.get("content-type") == "access-date":
                cit.remove(d)
                changed = True
    if changed:
        tree.write(jats_file, encoding="unicode")


def move_appendix_to_back(jats_file: str) -> None:
    """Move ``<sec id="appendix">`` from <body> into <back><app-group>."""
    tree = ET.parse(jats_file)
    root = tree.getroot()
    body = root.find(".//body")
    if body is None:
        return
    appendix = None
    for sec in list(body.findall("sec")):
        if sec.get("id") == "appendix":
            appendix = sec
            break
    if appendix is None:
        return
    body.remove(appendix)
    back = root.find("back")
    if back is None:
        back = ET.SubElement(root, "back")
    # Convert the <sec id="appendix"> into an <app id="appendix"> wrapped in an <app-group>
    app_group = back.find("app-group")
    if app_group is None:
        app_group = ET.SubElement(back, "app-group")
    appendix.tag = "app"
    app_group.append(appendix)
    tree.write(jats_file, encoding="unicode")


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def convert_quarto(input_qmd: Path, output_xml: Path, html: bool = False) -> None:
    """Convert a .qmd file to publisher-ready JATS XML.

    The caller is responsible for having already prepared the workspace
    (i.e. ``input_qmd.parent`` should be a writable copy of the source dir),
    matching the contract of :func:`latex_jats.convert.convert`.
    """
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    log_dir = output_xml.parent / "logs"

    logger.info("Will convert (quarto) %s -> %s", input_qmd, output_xml)

    # Step 1: render with quarto inside the workspace
    logger.info("Step 1: Rendering Quarto to JATS XML...")
    rendered = render_quarto(input_qmd, log_dir=log_dir)
    shutil.copy2(rendered, output_xml)

    # Step 2: post-processing
    logger.info("Step 2: Post-processing JATS XML...")
    out_str = str(output_xml)
    inject_metadata_from_yaml(out_str, str(input_qmd))
    fix_empty_history(out_str)
    fix_corresp_xref(out_str)
    unwrap_table_fig(out_str)
    add_fig_table_labels(out_str)
    drop_orphan_fns(out_str)
    move_fn_group_to_back(out_str)
    drop_empty_refs_section(out_str)
    clean_element_citations(out_str)
    move_appendix_to_back(out_str)
    fix_ext_links(out_str)
    fix_pdf_graphic_refs(out_str)
    finalize_xml(out_str)

    logger.info("Saved corrected JATS XML in %s", output_xml)

    # Step 2c: copy graphics from the workspace to the output directory.
    # Quarto produces figures under workspace/figures/ and may also place
    # other images directly in the source dir.
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".tif", ".tiff", ".pdf"}
    workspace_dir = input_qmd.parent
    copied = []
    for img in workspace_dir.rglob("*"):
        if img.is_file() and img.suffix.lower() in image_exts:
            rel = img.relative_to(workspace_dir)
            dest = output_xml.parent / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or img.stat().st_mtime > dest.stat().st_mtime:
                shutil.copy2(img, dest)
                copied.append(str(rel))
    if copied:
        logger.info("Copied %d image(s) to output", len(copied))

    # Step 2d: convert any remaining PDF graphics to SVG
    _convert_pdf_figures(out_str, workspace_dir)

    # Step 2e: rename graphics to publisher format (ID_fig1.ext, ...)
    rename_graphics(out_str)

    # Step 3 (optional): HTML preview
    if html:
        html_path = output_xml.with_suffix(".html")
        logger.info("Step 3: Generating HTML preview...")
        convert_to_html(out_str, str(html_path))
        logger.info("Saved HTML preview in %s", html_path)
