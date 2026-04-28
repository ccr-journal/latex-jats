import logging
import xml.etree.ElementTree as ET

from jatsmith.convert import dedupe_ref_lists


def _doc(body_xrefs="", ref_lists=""):
    return f"""<article>
  <front><article-meta><title-group><article-title>X</article-title></title-group></article-meta></front>
  <body>
    <sec><p>Citing {body_xrefs}.</p></sec>
  </body>
  <back>
{ref_lists}
  </back>
</article>"""


def _ref_list(prefix, n):
    refs = "".join(
        f'    <ref id="{prefix}.bibx{i}"><mixed-citation>Entry {i}</mixed-citation></ref>\n'
        for i in range(1, n + 1)
    )
    return f"  <ref-list>\n{refs}  </ref-list>"


def _ref_lists_in_back(path):
    tree = ET.parse(path)
    return tree.getroot().find("back").findall("ref-list")


def test_single_ref_list_is_noop(xml_file, caplog):
    p = xml_file(_doc(ref_lists=_ref_list("bib", 3)))
    with caplog.at_level(logging.WARNING):
        dedupe_ref_lists(p)
    assert len(_ref_lists_in_back(p)) == 1
    assert caplog.records == []


def test_no_back_is_noop(xml_file):
    p = xml_file("<article><body><p>No back element.</p></body></article>")
    dedupe_ref_lists(p)  # should not raise


def test_drops_orphan_ref_list_referenced_is_second(xml_file, caplog):
    # All body xrefs point to biba.* — bib.* is orphan.
    body_xrefs = '<xref rid="biba.bibx1">1</xref> <xref rid="biba.bibx2">2</xref>'
    p = xml_file(_doc(
        body_xrefs=body_xrefs,
        ref_lists=_ref_list("bib", 3) + "\n" + _ref_list("biba", 3),
    ))
    with caplog.at_level(logging.INFO):
        dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    ids = [r.get("id") for r in remaining[0].findall("ref")]
    assert ids == ["biba.bibx1", "biba.bibx2", "biba.bibx3"]


def test_drops_orphan_ref_list_referenced_is_first(xml_file):
    # Reverse case: body refs go to bib.*, biba.* is orphan.
    body_xrefs = '<xref rid="bib.bibx1">1</xref>'
    p = xml_file(_doc(
        body_xrefs=body_xrefs,
        ref_lists=_ref_list("bib", 3) + "\n" + _ref_list("biba", 3),
    ))
    dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    assert remaining[0].findall("ref")[0].get("id") == "bib.bibx1"


def test_three_ref_lists_keeps_referenced_middle(xml_file):
    body_xrefs = '<xref rid="middle.bibx2">2</xref>'
    p = xml_file(_doc(
        body_xrefs=body_xrefs,
        ref_lists=(
            _ref_list("bib", 3) + "\n"
            + _ref_list("middle", 3) + "\n"
            + _ref_list("biba", 3)
        ),
    ))
    dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    ids = [r.get("id") for r in remaining[0].findall("ref")]
    assert ids[0].startswith("middle.")


def test_no_xrefs_keeps_first_and_warns(xml_file, caplog):
    p = xml_file(_doc(
        body_xrefs="",
        ref_lists=_ref_list("bib", 3) + "\n" + _ref_list("biba", 3),
    ))
    with caplog.at_level(logging.WARNING):
        dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    assert remaining[0].findall("ref")[0].get("id") == "bib.bibx1"
    assert any("no <xref>" in r.message or "references any" in r.message
               for r in caplog.records)


def test_mixed_references_keeps_more_referenced(xml_file):
    # 3 refs to bib.*, 1 to biba.* → bib.* wins.
    body_xrefs = (
        '<xref rid="bib.bibx1">1</xref> '
        '<xref rid="bib.bibx2">2</xref> '
        '<xref rid="bib.bibx3">3</xref> '
        '<xref rid="biba.bibx1">a</xref>'
    )
    p = xml_file(_doc(
        body_xrefs=body_xrefs,
        ref_lists=_ref_list("bib", 3) + "\n" + _ref_list("biba", 3),
    ))
    dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    assert remaining[0].findall("ref")[0].get("id") == "bib.bibx1"


def test_xref_in_front_also_counts(xml_file):
    # If an abstract or front-matter cite uses biba.*, it should still count.
    doc = """<article>
  <front><article-meta>
    <abstract><p>See <xref rid="biba.bibx1">1</xref>.</p></abstract>
  </article-meta></front>
  <body><sec><p>Body text.</p></sec></body>
  <back>
{ref_lists}
  </back>
</article>""".format(ref_lists=_ref_list("bib", 2) + "\n" + _ref_list("biba", 2))
    p = xml_file(doc)
    dedupe_ref_lists(p)
    remaining = _ref_lists_in_back(p)
    assert len(remaining) == 1
    assert remaining[0].findall("ref")[0].get("id") == "biba.bibx1"
