"""Unit and integration tests for parse_bbl, fix_references, and _build_mixed_citation."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from latex_jats.convert import fix_references, parse_bbl

XLINK = 'http://www.w3.org/1999/xlink'

# ---------------------------------------------------------------------------
# Minimal .bbl helpers
# ---------------------------------------------------------------------------

def _bbl(entries_text):
    return (
        r'\refsection{0}' + '\n'
        r'  \datalist[entry]{nyt/global//global/global}' + '\n'
        + entries_text + '\n'
        r'  \enddatalist' + '\n'
        r'\endrefsection' + '\n'
    )



def _bbl_article_raw(key='smith2020', family='Smith', giveni='J.', year='2020',
                     title='A study', journal='Science', volume='10', number='2',
                     pages='1\\bibrangedash 5', doi=''):
    doi_block = (
        f'      \\verb{{doi}}\n      \\verb {doi}\n      \\endverb\n' if doi else ''
    )
    return _bbl(f"""\
    \\entry{{{key}}}{{article}}{{}}
      \\name{{author}}{{1}}{{}}{{%
        {{{{un=0,uniquepart=base,hash=abc}}{{%
           family={{{family}}},
           familyi={{S\\bibinitperiod}},
           given={{John}},
           giveni={{{giveni}}},
           givenun=0}}}}%
      }}
      \\field{{labelnamesource}}{{author}}
      \\field{{labeltitlesource}}{{title}}
      \\field{{title}}{{{title}}}
      \\field{{journaltitle}}{{{journal}}}
      \\field{{year}}{{{year}}}
      \\field{{volume}}{{{volume}}}
      \\field{{number}}{{{number}}}
      \\field{{pages}}{{{pages}}}
{doi_block}    \\endentry
""")


def _flat_jats(n=1):
    refs = ''.join(
        f'<ref id="bib.bibx{i+1}"><mixed-citation>Smith "A study" Science 10(2) 2020</mixed-citation></ref>\n'
        for i in range(n)
    )
    return f'<article><back><ref-list>{refs}</ref-list></back></article>'


# ---------------------------------------------------------------------------
# parse_bbl tests
# ---------------------------------------------------------------------------

def test_parse_bbl_basic(tmp_path):
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(_bbl_article_raw(), encoding='utf-8')
    entries = parse_bbl(bbl)
    assert len(entries) == 1
    e = entries[0]
    assert e['key'] == 'smith2020'
    assert e['type'] == 'article'
    assert e['authors'][0]['family'] == 'Smith'
    assert e['authors'][0]['given'] == 'J.'
    assert e['title'] == 'A study'
    assert e['journaltitle'] == 'Science'
    assert e['year'] == '2020'
    assert e['volume'] == '10'
    assert e['number'] == '2'
    assert '1' in e['pages'] and '5' in e['pages']


def test_parse_bbl_doi_via_verb(tmp_path):
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(_bbl_article_raw(doi='10.1000/test'), encoding='utf-8')
    entries = parse_bbl(bbl)
    assert entries[0].get('doi') == '10.1000/test'


def test_parse_bbl_url_via_verb(tmp_path):
    bbl_text = _bbl("""\
    \\entry{jones2021}{misc}{}
      \\name{author}{1}{}{%
        {{un=0,uniquepart=base,hash=xyz}{%
           family={Jones},
           familyi={J\\bibinitperiod},
           given={Alice},
           giveni={A\\bibinitperiod},
           givenun=0}}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{Some resource}
      \\field{year}{2021}
      \\verb{url}
      \\verb https://example.com/resource
      \\endverb
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')
    entries = parse_bbl(bbl)
    assert entries[0].get('url') == 'https://example.com/resource'


def test_parse_bbl_publisher_via_list(tmp_path):
    bbl_text = _bbl("""\
    \\entry{smith2020b}{book}{}
      \\name{author}{1}{}{%
        {{un=0,uniquepart=base,hash=abc}{%
           family={Smith},
           familyi={S\\bibinitperiod},
           given={John},
           giveni={J\\bibinitperiod},
           givenun=0}}%
      }
      \\list{publisher}{1}{%
        {Test Press}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{A book}
      \\field{year}{2020}
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')
    entries = parse_bbl(bbl)
    assert entries[0].get('publisher') == 'Test Press'


# ---------------------------------------------------------------------------
# fix_references — journal article
# ---------------------------------------------------------------------------

def test_journal_article_structured(tmp_path):
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(_bbl_article_raw(), encoding='utf-8')

    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(_flat_jats(1), encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')

    assert mc is not None
    assert mc.get('publication-type') == 'journal'
    assert mc.find('string-name/surname').text == 'Smith'
    assert mc.find('string-name/given-names').text == 'J.'
    assert mc.find('year').text == '2020'
    assert mc.find('article-title').text == 'A study'
    assert mc.find('source/italic').text == 'Science'
    assert mc.find('volume').text == '10'
    assert mc.find('issue').text == '2'
    assert mc.find('fpage').text == '1'
    assert mc.find('lpage').text == '5'


def test_journal_article_with_doi(tmp_path):
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(_bbl_article_raw(doi='10.1000/test'), encoding='utf-8')

    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(_flat_jats(1), encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')
    link = mc.find('ext-link')
    assert link is not None
    assert link.get('ext-link-type') == 'doi'
    assert '10.1000/test' in link.get(f'{{{XLINK}}}href', '')


# ---------------------------------------------------------------------------
# fix_references — book
# ---------------------------------------------------------------------------

def test_book_structured(tmp_path):
    bbl_text = _bbl("""\
    \\entry{dittmar2015}{book}{}
      \\name{author}{1}{}{%
        {{un=0,uniquepart=base,hash=abc}{%
           family={Dittmar},
           familyi={D\\bibinitperiod},
           given={Kelly},
           giveni={K\\bibinitperiod},
           givenun=0}}%
      }
      \\list{publisher}{1}{%
        {Temple University Press}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{Navigating gendered terrain}
      \\field{year}{2015}
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')

    flat = '<article><back><ref-list><ref id="bib.bibx1"><mixed-citation>Dittmar 2015</mixed-citation></ref></ref-list></back></article>'
    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(flat, encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')

    assert mc.get('publication-type') == 'book'
    assert mc.find('source/italic').text == 'Navigating gendered terrain'
    assert mc.find('article-title') is None  # no article-title for books
    assert mc.find('publisher-name').text == 'Temple University Press'


# ---------------------------------------------------------------------------
# fix_references — multiple authors (& separator)
# ---------------------------------------------------------------------------

def test_multiple_authors_separator(tmp_path):
    bbl_text = _bbl("""\
    \\entry{jones2020}{article}{}
      \\name{author}{3}{}{%
        {{un=0,uniquepart=base,hash=a}{%
           family={Jones},familyi={J\\bibinitperiod},given={Alice},giveni={A\\bibinitperiod},givenun=0}}%
        {{un=0,uniquepart=base,hash=b}{%
           family={Brown},familyi={B\\bibinitperiod},given={Bob},giveni={B\\bibinitperiod},givenun=0}}%
        {{un=0,uniquepart=base,hash=c}{%
           family={Smith},familyi={S\\bibinitperiod},given={Carol},giveni={C\\bibinitperiod},givenun=0}}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{A collaborative study}
      \\field{journaltitle}{Nature}
      \\field{year}{2020}
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')

    flat = '<article><back><ref-list><ref id="bib.bibx1"><mixed-citation>Jones Brown Smith 2020</mixed-citation></ref></ref-list></back></article>'
    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(flat, encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')

    names = mc.findall('string-name')
    assert len(names) == 3
    # second-to-last author's tail should contain & separator
    assert '\u0026' in (names[1].tail or ''), f"Expected & in tail: {names[1].tail!r}"
    # first author's tail should contain comma
    assert ',' in (names[0].tail or ''), f"Expected comma in tail: {names[0].tail!r}"


# ---------------------------------------------------------------------------
# fix_references — collab (organization author)
# ---------------------------------------------------------------------------

def test_collab_entry(tmp_path):
    bbl_text = _bbl("""\
    \\entry{dailykos2016}{misc}{}
      \\name{author}{1}{}{%
        {{un=0,uniquepart=base,hash=xyz}{%
           family={{Daily Kos Election}},
           familyi={D\\bibinitperiod}}}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{Daily Kos Elections Guide}
      \\field{year}{2016}
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')

    flat = '<article><back><ref-list><ref id="bib.bibx1"><mixed-citation>Daily Kos Election 2016</mixed-citation></ref></ref-list></back></article>'
    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(flat, encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')

    assert mc.get('publication-type') == 'collab'
    collab = mc.find('collab')
    assert collab is not None
    assert 'Daily Kos Election' in collab.text
    assert mc.find('string-name') is None


# ---------------------------------------------------------------------------
# fix_references — URL (no DOI)
# ---------------------------------------------------------------------------

def test_url_without_doi(tmp_path):
    bbl_text = _bbl("""\
    \\entry{jones2021}{misc}{}
      \\name{author}{1}{}{%
        {{un=0,uniquepart=base,hash=xyz}{%
           family={Jones},
           familyi={J\\bibinitperiod},
           given={Alice},
           giveni={A\\bibinitperiod},
           givenun=0}}%
      }
      \\field{labelnamesource}{author}
      \\field{labeltitlesource}{title}
      \\field{title}{Some resource}
      \\field{year}{2021}
      \\verb{url}
      \\verb https://example.com/resource
      \\endverb
    \\endentry
""")
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(bbl_text, encoding='utf-8')

    flat = '<article><back><ref-list><ref id="bib.bibx1"><mixed-citation>Jones 2021</mixed-citation></ref></ref-list></back></article>'
    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(flat, encoding='utf-8')

    fix_references(str(xml_path), str(bbl))
    root = ET.parse(xml_path).getroot()
    mc = root.find('.//mixed-citation')
    link = mc.find('ext-link')
    assert link is not None
    assert link.get('ext-link-type') == 'uri'
    assert link.get(f'{{{XLINK}}}href') == 'https://example.com/resource'


# ---------------------------------------------------------------------------
# fix_references — count mismatch doesn't crash
# ---------------------------------------------------------------------------

def test_count_mismatch_no_crash(tmp_path):
    # 1 bbl entry but 2 refs
    bbl = tmp_path / 'test.bbl'
    bbl.write_text(_bbl_article_raw(), encoding='utf-8')

    xml_path = tmp_path / 'test.xml'
    xml_path.write_text(_flat_jats(2), encoding='utf-8')

    fix_references(str(xml_path), str(bbl))  # should not raise
    root = ET.parse(xml_path).getroot()
    refs = root.findall('.//ref')
    assert len(refs) == 2  # both refs still present


# ---------------------------------------------------------------------------
# Integration test against YAO gold file
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / 'fixtures' / 'latex'
YAO_TEX = FIXTURES / 'CCR2025.1.2.YAO' / 'main.tex'
YAO_GOLD = PROJECT_ROOT / 'CCR2025.1.2.YAO_gold' / 'CCR2025.1.2.YAO.xml'


@pytest.mark.integration
@pytest.mark.skipif(not YAO_TEX.exists() or not YAO_GOLD.exists(),
                    reason='YAO example files not found')
def test_yao_references_match_gold(tmp_path):
    """Full pipeline on YAO article; spot-check ref-list against gold."""
    import shutil
    from latex_jats.convert import (
        clean_body, fix_citation_ref_types, fix_footnotes, fix_metadata,
        fix_references, fix_table_notes, preprocess_for_latexml, run_latexmlc,
    )

    workspace = tmp_path / 'workspace'
    shutil.copytree(YAO_TEX.parent, workspace)
    preprocess_for_latexml(workspace)
    workspace_tex = workspace / YAO_TEX.name

    output = tmp_path / 'output.xml'
    run_latexmlc(str(workspace_tex), str(output), log_dir=tmp_path)
    fix_citation_ref_types(str(output))
    fix_metadata(str(output), str(YAO_TEX))
    fix_table_notes(str(output))
    clean_body(str(output))
    fix_footnotes(str(output))
    bbl = YAO_TEX.with_suffix('.bbl')
    fix_references(str(output), str(bbl))

    root = ET.parse(output).getroot()
    gold_root = ET.parse(YAO_GOLD).getroot()

    refs = root.findall('.//ref')
    gold_refs = gold_root.findall('.//ref')
    assert len(refs) == len(gold_refs), f'Ref count mismatch: {len(refs)} vs {len(gold_refs)}'

    # Every mixed-citation should have a publication-type
    for ref in refs:
        mc = ref.find('mixed-citation')
        assert mc is not None and mc.get('publication-type'), \
            f"Ref {ref.get('id')} missing publication-type"

    # First ref: Barry et al. 2020 journal article
    first_mc = refs[0].find('mixed-citation')
    assert first_mc.get('publication-type') == 'journal'
    surnames = [sn.find('surname').text for sn in first_mc.findall('string-name')]
    assert 'Barry' in surnames
    assert first_mc.find('year').text == '2020'
    assert first_mc.find('volume').text == '39'
    assert first_mc.find('issue').text == '2'
    assert first_mc.find('fpage').text == '327'
    assert first_mc.find('lpage').text == '333'

    # Dittmar (book, 8th ref 0-indexed = bib.bibx8 in output)
    dittmar_refs = [r for r in refs
                    if r.find('.//mixed-citation[@publication-type="book"]') is not None
                    and any('Dittmar' in (sn.find('surname').text or '')
                            for sn in r.findall('.//string-name'))]
    assert dittmar_refs, 'Dittmar book ref not found'
    dittmar_mc = dittmar_refs[0].find('mixed-citation')
    assert dittmar_mc.find('source') is not None
    assert dittmar_mc.find('publisher-name') is not None
    assert dittmar_mc.find('article-title') is None

    # Daily Kos: collab entry
    collab_refs = [r for r in refs
                   if r.find('.//mixed-citation[@publication-type="collab"]') is not None]
    assert collab_refs, 'No collab refs found'
    assert collab_refs[0].find('.//collab') is not None
