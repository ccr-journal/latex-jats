"""Unit tests for the upstream-source linkage helpers (Issue #7).

Covers the pure helpers (username derivation, Fernet round-trip) and the
fetch_upstream orchestration, which is exercised with a fake ``git clone``
command so these tests don't depend on the network.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
from cryptography.fernet import Fernet

from web.backend.app import upstream as upstream_module
from web.backend.app.config import AuthConfig, set_for_tests
from web.backend.app.upstream import (
    UpstreamError,
    UpstreamTokenUndecryptable,
    decrypt_token,
    derive_git_username,
    encrypt_token,
    fetch_upstream,
    is_upload_url,
)


FIXED_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _pin_config():
    set_for_tests(AuthConfig(
        editor_credentials={"editor": "testpass"},
        frontend_url="http://testserver",
        ojs_base_url="https://ojs",
        ojs_journal_path="ccr",
        ojs_admin_token="",
        ojs_doi_prefix="10.5117/",
        session_token_ttl_days=30,
        storage_secret_key=FIXED_KEY,
    ))
    upstream_module.reset_fernet_for_tests()
    yield
    upstream_module.reset_fernet_for_tests()


# ── derive_git_username ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://git.overleaf.com/abc123", "git"),
        ("https://www.overleaf.com/project/abc", "git"),
        ("https://github.com/user/repo.git", "x-access-token"),
        ("https://gitlab.com/group/project.git", "x-access-token"),
        ("https://example.com/repo.git", "x-access-token"),
    ],
)
def test_derive_git_username(url, expected):
    assert derive_git_username(url) == expected


# ── is_upload_url ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected",
    [
        ("file:///path/to/source", True),
        ("https://github.com/x/y", False),
        ("", False),
        (None, False),
        ("ssh://git@host/repo", False),
    ],
)
def test_is_upload_url(url, expected):
    assert is_upload_url(url) is expected


# ── Fernet round-trip ────────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip():
    ct = encrypt_token("secret-pat-123")
    assert ct != b"secret-pat-123"
    assert decrypt_token(ct) == "secret-pat-123"


def test_decrypt_with_different_key_raises():
    ct = encrypt_token("original")
    # Rotate the key and try to decrypt the old ciphertext.
    set_for_tests(AuthConfig(
        editor_credentials={"editor": "testpass"},
        frontend_url="http://testserver",
        ojs_base_url="https://ojs",
        ojs_journal_path="ccr",
        ojs_admin_token="",
        ojs_doi_prefix="10.5117/",
        session_token_ttl_days=30,
        storage_secret_key=Fernet.generate_key().decode(),
    ))
    upstream_module.reset_fernet_for_tests()
    with pytest.raises(UpstreamTokenUndecryptable):
        decrypt_token(ct)


# ── fetch_upstream orchestration ─────────────────────────────────────────────


@dataclass
class FakeManuscript:
    upstream_url: str
    upstream_token_encrypted: Optional[bytes] = None
    upstream_ref: Optional[str] = None
    upstream_subpath: Optional[str] = None


def _install_fake_git(monkeypatch, seeded_repo_factory):
    """Replace subprocess.run so `git clone` populates a dest dir with seed files.

    seeded_repo_factory(dest: Path) is called to lay down the repo contents.
    """
    real_run = subprocess.run
    invocations: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        invocations.append(list(cmd))
        if cmd[:2] == ["git", "clone"]:
            # Parse out the destination — it's the last positional arg.
            dest = Path(cmd[-1])
            dest.mkdir(parents=True, exist_ok=True)
            seeded_repo_factory(dest)
            # Simulate a .git dir so rev-parse can be stubbed below.
            (dest / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "-C"] and cmd[3:5] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef\n", stderr="")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return invocations


def test_fetch_upstream_public_clone(tmp_path, monkeypatch):
    def seed(dest: Path) -> None:
        (dest / "main.tex").write_text("\\documentclass{article}")
        (dest / "refs.bib").write_text("@article{x, title={x}}")

    _install_fake_git(monkeypatch, seed)

    ms = FakeManuscript(upstream_url="https://github.com/user/repo.git")
    source_dir = tmp_path / "source"
    sha = fetch_upstream(ms, source_dir)

    assert sha == "deadbeef"
    assert (source_dir / "main.tex").exists()
    assert (source_dir / "refs.bib").exists()
    # .git should be scrubbed from the final source_dir
    assert not (source_dir / ".git").exists()


def test_fetch_upstream_subpath(tmp_path, monkeypatch):
    def seed(dest: Path) -> None:
        (dest / "README.md").write_text("top-level")
        paper = dest / "paper"
        paper.mkdir()
        (paper / "main.tex").write_text("inside paper dir")
        (paper / "refs.bib").write_text("@x{y}")

    _install_fake_git(monkeypatch, seed)

    ms = FakeManuscript(
        upstream_url="https://github.com/user/repo.git",
        upstream_subpath="paper",
    )
    source_dir = tmp_path / "source"
    fetch_upstream(ms, source_dir)

    assert (source_dir / "main.tex").exists()
    assert (source_dir / "refs.bib").exists()
    # The non-subpath content must be dropped
    assert not (source_dir / "README.md").exists()


def test_fetch_upstream_flattens_single_wrapper_dir(tmp_path, monkeypatch):
    def seed(dest: Path) -> None:
        wrapper = dest / "my-paper"
        wrapper.mkdir()
        (wrapper / "main.tex").write_text("hi")

    _install_fake_git(monkeypatch, seed)

    ms = FakeManuscript(upstream_url="https://github.com/user/repo.git")
    source_dir = tmp_path / "source"
    fetch_upstream(ms, source_dir)

    # Wrapper lifted — main.tex sits directly in source_dir
    assert (source_dir / "main.tex").exists()
    assert not (source_dir / "my-paper").exists()


def test_fetch_upstream_rejects_upload_url(tmp_path):
    ms = FakeManuscript(upstream_url="file:///tmp/x")
    with pytest.raises(UpstreamError, match="uploaded directly"):
        fetch_upstream(ms, tmp_path / "source")


def test_fetch_upstream_token_not_in_command_line(tmp_path, monkeypatch):
    """The token must be passed via env, never embedded in the git clone argv."""
    def seed(dest: Path) -> None:
        (dest / "main.tex").write_text("ok")

    invocations = _install_fake_git(monkeypatch, seed)

    ct = encrypt_token("super-secret-pat-abc123")
    ms = FakeManuscript(
        upstream_url="https://github.com/user/private.git",
        upstream_token_encrypted=ct,
    )
    fetch_upstream(ms, tmp_path / "source")

    # The clone invocation should not contain the token literally
    clone_cmds = [c for c in invocations if c[:2] == ["git", "clone"]]
    assert clone_cmds, "expected a git clone invocation"
    for arg in clone_cmds[0]:
        assert "super-secret-pat-abc123" not in arg


def test_fetch_upstream_propagates_git_failure(tmp_path, monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            return subprocess.CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: repository not found\n",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ms = FakeManuscript(upstream_url="https://github.com/user/nope.git")
    with pytest.raises(UpstreamError, match="repository not found"):
        fetch_upstream(ms, tmp_path / "source")


def test_fetch_upstream_replaces_existing_source(tmp_path, monkeypatch):
    def seed(dest: Path) -> None:
        (dest / "new.tex").write_text("new")

    _install_fake_git(monkeypatch, seed)

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "stale.txt").write_text("should be gone")

    ms = FakeManuscript(upstream_url="https://github.com/user/repo.git")
    fetch_upstream(ms, source_dir)

    assert (source_dir / "new.tex").exists()
    assert not (source_dir / "stale.txt").exists()
