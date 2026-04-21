"""Unit tests for latex_jats.web.ojs parsing helpers."""

from __future__ import annotations

from web.backend.app.ojs import _parse_authors


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
