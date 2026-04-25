"""Unit tests for jatsmith.web.ojs parsing helpers."""

from __future__ import annotations

from dataclasses import replace

from web.backend.app.ojs import (
    OjsSubmission,
    _enrich_from_decisions,
    _enrich_from_publication,
    _iso_date,
    _parse_authors,
    _parse_submission,
)


def _author(aid: int, given: str, family: str, seq: int, email: str | None = None) -> dict:
    return {
        "id": aid,
        "givenName": {"en": given},
        "familyName": {"en": family},
        "email": email,
        "seq": seq,
    }


def test_parse_authors_flags_primary_contact():
    publication = {
        "primaryContactId": 22,
        "authors": [
            _author(11, "Alice", "Adams", seq=0, email="a@example.org"),
            _author(22, "Bob", "Brown", seq=1, email="b@example.org"),
        ],
    }
    authors = _parse_authors(publication)
    assert len(authors) == 2
    by_name = {a.name: a for a in authors}
    assert by_name["Alice Adams"].primary_contact is False
    assert by_name["Bob Brown"].primary_contact is True


def test_parse_authors_no_primary_contact_id():
    publication = {
        "authors": [
            _author(11, "Alice", "Adams", seq=0),
            _author(22, "Bob", "Brown", seq=1),
        ],
    }
    authors = _parse_authors(publication)
    assert all(a.primary_contact is False for a in authors)


def test_parse_authors_primary_contact_id_no_match():
    publication = {
        "primaryContactId": 999,
        "authors": [
            _author(11, "Alice", "Adams", seq=0),
            _author(22, "Bob", "Brown", seq=1),
        ],
    }
    authors = _parse_authors(publication)
    assert all(a.primary_contact is False for a in authors)


def test_parse_authors_sorts_by_seq():
    publication = {
        "primaryContactId": 11,
        "authors": [
            _author(22, "Bob", "Brown", seq=1),
            _author(11, "Alice", "Adams", seq=0),
        ],
    }
    authors = _parse_authors(publication)
    assert [a.name for a in authors] == ["Alice Adams", "Bob Brown"]
    assert authors[0].primary_contact is True


# ── Date handling ────────────────────────────────────────────────────────────


def test_iso_date_strips_time():
    # OJS returns "YYYY-MM-DD HH:MM:SS" for submission and decision timestamps
    assert _iso_date("2025-05-28 16:43:54") == "2025-05-28"


def test_iso_date_passes_date_only_through():
    # Publication dates are already YYYY-MM-DD
    assert _iso_date("2026-02-16") == "2026-02-16"


def test_iso_date_returns_none_for_empty_or_missing():
    assert _iso_date(None) is None
    assert _iso_date("") is None
    assert _iso_date("   ") is None


def _submission_item(
    submission_id: int = 9241,
    date_submitted: str | None = "2025-05-28 16:43:54",
    doi: str = "10.5117/CCR2026.1.2.SMITH",
) -> dict:
    return {
        "id": submission_id,
        "dateSubmitted": date_submitted,
        "publications": [{
            "id": 7764,
            "doiObject": {"doi": doi},
            "title": {"en": "A Title"},
        }],
        "currentPublicationId": 7764,
    }


def test_parse_submission_captures_date_received():
    item = _submission_item()
    parsed = _parse_submission(item, doi_prefix="10.5117/")
    assert parsed is not None
    sub, _ = parsed
    assert sub.date_received == "2025-05-28"


def test_parse_submission_missing_date_submitted():
    item = _submission_item(date_submitted=None)
    parsed = _parse_submission(item, doi_prefix="10.5117/")
    assert parsed is not None
    sub, _ = parsed
    assert sub.date_received is None


def test_enrich_from_publication_captures_date_published():
    sub = OjsSubmission(submission_id=1, doi_suffix="CCR2026.1.2.X", title="T")
    publication = {
        "datePublished": "2026-02-16",
        "authors": [],
        "abstract": {"en": ""},
        "keywords": {},
    }
    enriched = _enrich_from_publication(sub, publication)
    assert enriched.date_published == "2026-02-16"


def test_enrich_from_publication_missing_date_published():
    sub = OjsSubmission(submission_id=1, doi_suffix="CCR2026.1.2.X", title="T")
    publication = {"authors": [], "abstract": {"en": ""}, "keywords": {}}
    enriched = _enrich_from_publication(sub, publication)
    assert enriched.date_published is None


def _decision(code: int, date: str) -> dict:
    return {"decision": code, "dateDecided": date}


def test_enrich_from_decisions_accept_submission():
    """Decision code 2 ("Accept Submission") sets date_accepted."""
    sub = OjsSubmission(submission_id=9241, doi_suffix="X", title="T")
    decisions = [
        _decision(3, "2025-06-10 13:53:48"),   # Send for Review
        _decision(5, "2025-08-20 20:14:14"),   # Resubmit for Review
        _decision(2, "2026-01-14 11:51:41"),   # Accept Submission
        _decision(7, "2026-02-16 15:44:16"),   # Send To Production
    ]
    enriched = _enrich_from_decisions(sub, decisions)
    assert enriched.date_accepted == "2026-01-14"


def test_enrich_from_decisions_accept_and_skip_review():
    """Decision code 17 ("Accept and Skip Review") also counts."""
    sub = OjsSubmission(submission_id=8896, doi_suffix="X", title="T")
    decisions = [
        _decision(17, "2024-12-16 12:00:26"),
        _decision(7, "2024-12-16 12:01:03"),
    ]
    enriched = _enrich_from_decisions(sub, decisions)
    assert enriched.date_accepted == "2024-12-16"


def test_enrich_from_decisions_no_accept_warns(caplog):
    """Decision list without an accept code leaves date_accepted=None and warns."""
    sub = OjsSubmission(submission_id=8597, doi_suffix="X", title="T")
    decisions = [
        _decision(19, "2024-07-24 09:41:11"),  # legacy code, not in accept set
        _decision(7, "2024-07-24 09:41:27"),
    ]
    with caplog.at_level("WARNING", logger="jatsmith.web.ojs"):
        enriched = _enrich_from_decisions(sub, decisions)
    assert enriched.date_accepted is None
    assert any(
        "no Accept Submission / Accept and Skip Review" in rec.message
        for rec in caplog.records
    )


def test_enrich_from_decisions_picks_latest_accept():
    """When multiple accepts exist (unusual but possible), take the most recent."""
    sub = OjsSubmission(submission_id=1, doi_suffix="X", title="T")
    decisions = [
        _decision(2, "2025-09-01 10:00:00"),
        _decision(2, "2026-01-14 11:00:00"),
    ]
    enriched = _enrich_from_decisions(sub, decisions)
    assert enriched.date_accepted == "2026-01-14"


def test_enrich_from_decisions_empty_list():
    sub = OjsSubmission(submission_id=1, doi_suffix="X", title="T")
    enriched = _enrich_from_decisions(sub, [])
    assert enriched.date_accepted is None
