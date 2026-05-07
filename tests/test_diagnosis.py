"""Tests for the Claude diagnosis chat (Issue #36).

The Anthropic SDK is monkeypatched so we never make a real network call.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import Session

from web.backend.app import diagnosis
from web.backend.app.models import (
    DiagnosisChat,
    Manuscript,
    ManuscriptStatus,
)

# Reuse the fixtures from test_web_api so we get the same
# editor/author/anon clients and the seeded site config.
from tests.test_web_api import (  # noqa: F401
    AUTHOR_FIXTURE_DOI,
    EDITOR_TOKEN,
    anon_client,
    author_client,
    client,
    engine,
    test_storage,
    _test_config,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────


def _fake_assistant_turn(text: str = "Looks like you have an unclosed environment.\n\n— Claude's guess; please verify."):
    return diagnosis.AssistantTurn(
        content=text,
        input_tokens=12345,
        output_tokens=234,
        cache_read_tokens=11_000,
    )


@pytest.fixture
def fake_claude(monkeypatch):
    """Replace diagnosis.call_claude with a deterministic fake.

    Returns the captured `messages` from the most recent call so tests
    can assert on what was sent (e.g. that the first turn includes the
    failure context).
    """
    captured: dict[str, list] = {"last_messages": []}

    def fake(messages: list[dict]) -> diagnosis.AssistantTurn:
        captured["last_messages"] = messages
        return _fake_assistant_turn()

    monkeypatch.setattr(diagnosis, "call_claude", fake)
    return captured


@pytest.fixture
def claude_enabled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_failed_manuscript(engine, test_storage, doi: str) -> None:
    """Create a manuscript with a failed convert step and a tiny .tex source."""
    source = test_storage.source_dir(doi)
    source.mkdir(parents=True, exist_ok=True)
    (source / "main.tex").write_text(
        r"\documentclass{ccr}\begin{document}Hello\end{document}",
        encoding="utf-8",
    )
    with Session(engine) as session:
        session.add(
            Manuscript(
                doi_suffix=doi,
                status=ManuscriptStatus.failed,
                title="A test article",
                main_file="main.tex",
                pipeline_steps=[
                    {
                        "name": "convert",
                        "status": "failed",
                        "logs": [
                            {
                                "name": "pipeline",
                                "content": "ERROR: latexml exited with code 1",
                            },
                            {
                                "name": "latexml",
                                "content": "Missing $ inserted at line 17.",
                            },
                        ],
                        "started_at": None,
                        "completed_at": None,
                    },
                ],
            )
        )
        session.commit()


# ── /api/auth/me flag ─────────────────────────────────────────────────────────


def test_me_reports_claude_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["claude_api_enabled"] is False


def test_me_reports_claude_enabled_when_key_present(client, claude_enabled):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["claude_api_enabled"] is True


# ── 503 / scoping ─────────────────────────────────────────────────────────────


def test_post_message_503_when_no_api_key(client, engine, test_storage, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _make_failed_manuscript(engine, test_storage, "CCR2025.1.1.NOKEY")
    r = client.post(
        "/api/manuscripts/CCR2025.1.1.NOKEY/diagnosis/messages",
        json={"content": ""},
    )
    assert r.status_code == 503


def test_get_diagnosis_404_for_unscoped_author(author_client, engine, test_storage):
    _make_failed_manuscript(engine, test_storage, "CCR2025.1.1.OTHER")
    # Author's token is scoped to AUTHOR_FIXTURE_DOI, not OTHER.
    r = author_client.get("/api/manuscripts/CCR2025.1.1.OTHER/diagnosis")
    assert r.status_code == 404


# ── Happy path: first turn seeds context, persistence, follow-ups ─────────────


def test_first_message_seeds_failure_context(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.SEED"
    _make_failed_manuscript(engine, test_storage, doi)
    # Drop a sibling .bib and a chapter .tex to verify the bundle picks up
    # everything Claude needs (option 2: walk the source tree).
    source = test_storage.source_dir(doi)
    (source / "refs.bib").write_text(
        "@article{smith2020, title = {A study}, author = {Smith}, year = {2020}}",
        encoding="utf-8",
    )
    (source / "chapter.tex").write_text(
        r"\section{Methods}This is the chapter file.", encoding="utf-8"
    )

    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": ""},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["manuscript_id"] == doi
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert "guess" in data["messages"][1]["content"].lower()
    assert data["messages"][1]["input_tokens"] == 12345
    assert data["messages"][1]["cache_read_tokens"] == 11_000

    # The wire payload sent to Claude should contain the failed-step log,
    # the main file, and any sibling .tex / .bib files.
    sent = fake_claude["last_messages"]
    assert len(sent) == 1
    assert sent[0]["role"] == "user"
    body = sent[0]["content"]
    assert "Missing $ inserted at line 17" in body
    assert "Hello" in body                  # main.tex body
    assert "main.tex" in body
    assert "smith2020" in body              # refs.bib content
    assert "refs.bib" in body
    assert "chapter file" in body           # chapter.tex content
    # Main file must appear before the others so it dominates attention.
    assert body.index("main.tex") < body.index("refs.bib")


def test_chat_persists_and_followups_append(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.FOLLOW"
    _make_failed_manuscript(engine, test_storage, doi)

    client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": ""},
    )
    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": "What about the bibliography?"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["messages"]) == 4
    assert data["messages"][2]["content"] == "What about the bibliography?"

    # GET returns the same chat.
    r = client.get(f"/api/manuscripts/{doi}/diagnosis")
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 4


def test_get_returns_null_when_no_chat(client, engine, test_storage):
    _make_failed_manuscript(engine, test_storage, "CCR2025.1.1.NONE")
    r = client.get("/api/manuscripts/CCR2025.1.1.NONE/diagnosis")
    assert r.status_code == 200
    assert r.json() is None


# ── Rate limit ────────────────────────────────────────────────────────────────


def test_rate_limit_kicks_in_after_five_user_messages(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.LIMIT"
    _make_failed_manuscript(engine, test_storage, doi)

    # Pre-seed the chat with 5 recent user messages so the next post 429s
    # without us having to actually call the route 5 times (faster + clearer).
    now = datetime.utcnow()
    with Session(engine) as session:
        session.add(
            DiagnosisChat(
                manuscript_id=doi,
                messages=[
                    {
                        "role": "user",
                        "content": f"q{i}",
                        "created_at": (now - timedelta(minutes=i)).isoformat(),
                    }
                    for i in range(5)
                ],
            )
        )
        session.commit()

    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": "one more please"},
    )
    assert r.status_code == 429


# ── Editor reset ──────────────────────────────────────────────────────────────


def test_editor_can_reset_chat(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.RESET"
    _make_failed_manuscript(engine, test_storage, doi)
    client.post(f"/api/manuscripts/{doi}/diagnosis/messages", json={"content": ""})

    r = client.delete(f"/api/manuscripts/{doi}/diagnosis")
    assert r.status_code == 204
    r = client.get(f"/api/manuscripts/{doi}/diagnosis")
    assert r.status_code == 200
    assert r.json() is None


def test_author_can_reset_their_own_chat(
    author_client, engine, test_storage, claude_enabled, fake_claude
):
    # author_client is scoped to AUTHOR_FIXTURE_DOI; need a chat there first.
    source = test_storage.source_dir(AUTHOR_FIXTURE_DOI)
    source.mkdir(parents=True, exist_ok=True)
    (source / "main.tex").write_text(r"\documentclass{ccr}", encoding="utf-8")

    author_client.post(
        f"/api/manuscripts/{AUTHOR_FIXTURE_DOI}/diagnosis/messages",
        json={"content": ""},
    )
    r = author_client.delete(f"/api/manuscripts/{AUTHOR_FIXTURE_DOI}/diagnosis")
    assert r.status_code == 204
    r = author_client.get(f"/api/manuscripts/{AUTHOR_FIXTURE_DOI}/diagnosis")
    assert r.status_code == 200
    assert r.json() is None


def test_chat_marked_stale_after_reconversion(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.STALE"
    _make_failed_manuscript(engine, test_storage, doi)
    client.post(f"/api/manuscripts/{doi}/diagnosis/messages", json={"content": ""})

    # Simulate a re-conversion completing after the chat was created.
    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        assert ms is not None
        ms.job_completed_at = datetime.utcnow() + timedelta(minutes=1)
        session.add(ms)
        session.commit()

    r = client.get(f"/api/manuscripts/{doi}/diagnosis")
    assert r.status_code == 200
    assert r.json()["is_stale"] is True


def test_post_409_on_stale_chat(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.STALE2"
    _make_failed_manuscript(engine, test_storage, doi)
    client.post(f"/api/manuscripts/{doi}/diagnosis/messages", json={"content": ""})

    with Session(engine) as session:
        ms = session.get(Manuscript, doi)
        assert ms is not None
        ms.job_completed_at = datetime.utcnow() + timedelta(minutes=1)
        session.add(ms)
        session.commit()

    # Author follow-up after re-conversion is rejected.
    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": "what about the figures?"},
    )
    assert r.status_code == 409
    # Clearing then starting fresh works.
    assert client.delete(f"/api/manuscripts/{doi}/diagnosis").status_code == 204
    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages", json={"content": ""}
    )
    # The new chat is created "now", but in this test job_completed_at was
    # set to a future timestamp to force the stale state — so the new chat
    # also reads as stale. In real use, new chats are created after the
    # conversion completes, so created_at > job_completed_at and is_stale
    # is False.
    assert r.status_code == 200


def test_include_source_false_omits_source_files(
    client, engine, test_storage, claude_enabled, fake_claude
):
    doi = "CCR2025.1.1.NOSRC"
    _make_failed_manuscript(engine, test_storage, doi)
    # Make sure there's something to omit.
    source = test_storage.source_dir(doi)
    (source / "refs.bib").write_text("@article{x, title={Y}}", encoding="utf-8")

    r = client.post(
        f"/api/manuscripts/{doi}/diagnosis/messages",
        json={"content": "", "include_source": False},
    )
    assert r.status_code == 200
    body = fake_claude["last_messages"][0]["content"]
    # Logs still attached, but no source-file blocks.
    assert "Missing $ inserted at line 17" in body
    assert "main.tex" not in body
    assert "refs.bib" not in body
    assert "# Source:" not in body
