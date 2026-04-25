"""Upstream source linkage: encryption + git fetch (Issue #7).

This module handles the "Sync from upstream" flow. Manuscripts can be linked to
a git remote (public, GitHub with PAT, or Overleaf with personal access token);
fetch_upstream clones the remote into a temp directory, flattens a single
wrapper dir or applies an optional subpath, then atomically swaps the new tree
into the manuscript's source_dir.

Tokens are stored Fernet-encrypted in Manuscript.upstream_token_encrypted. When
STORAGE_SECRET_KEY is unset in the environment (dev convenience), we mint an
ephemeral key at import time and log a loud warning — any stored tokens then
become undecryptable across restarts, which is acceptable for dev.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from .config import get_config

logger = logging.getLogger("latex_jats.web.upstream")


# ── Schemes ────────────────────────────────────────────────────────────────────

UPLOAD_URL_SCHEME = "file"  # file:// URLs mark upload-sourced manuscripts

_GIT_USERNAME_BY_HOST = {
    "git.overleaf.com": "git",
    "www.overleaf.com": "git",
}
_DEFAULT_GIT_USERNAME = "x-access-token"  # GitHub / GitLab / generic


def is_upload_url(url: str | None) -> bool:
    """True if the url is a local-upload sentinel (file://)."""
    if not url:
        return False
    return urlparse(url).scheme == UPLOAD_URL_SCHEME


def derive_git_username(url: str) -> str:
    """Return the git username to pair with a token for this host.

    Overleaf expects literally ``git``; GitHub and GitLab fine-grained PATs go
    in as ``x-access-token``. Anything unknown defaults to ``x-access-token``.
    """
    host = (urlparse(url).hostname or "").lower()
    return _GIT_USERNAME_BY_HOST.get(host, _DEFAULT_GIT_USERNAME)


# ── Encryption ─────────────────────────────────────────────────────────────────

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    key = get_config().storage_secret_key
    if not key:
        # Dev convenience: ephemeral key. Warn loudly so production ops see it.
        logger.warning(
            "STORAGE_SECRET_KEY is not set — generating an ephemeral Fernet key. "
            "Any upstream tokens stored in this process will become "
            "undecryptable on restart. Set STORAGE_SECRET_KEY in production."
        )
        key = Fernet.generate_key().decode()
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def reset_fernet_for_tests() -> None:
    """Force the Fernet singleton to be re-initialized from current config."""
    global _fernet
    _fernet = None


def encrypt_token(plaintext: str) -> bytes:
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    try:
        return _get_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise UpstreamTokenUndecryptable(
            "Stored token could not be decrypted — STORAGE_SECRET_KEY may have "
            "changed. Re-enter the token on the Link upstream form."
        ) from exc


# ── Exceptions ─────────────────────────────────────────────────────────────────


class UpstreamError(Exception):
    """Raised when a sync from upstream fails for a user-visible reason."""


class UpstreamTokenUndecryptable(UpstreamError):
    pass


# ── Git fetch ──────────────────────────────────────────────────────────────────


def _write_askpass_script(token: str, tmpdir: Path) -> Path:
    """Write a tiny GIT_ASKPASS helper that prints the token on stdout.

    git calls GIT_ASKPASS with a prompt like ``Password for 'https://...':``.
    We respond with the token for any prompt — safe because the helper only
    exists inside this function's tmpdir and is chmod 700.
    """
    script = tmpdir / "askpass.sh"
    # Use /bin/sh and echo the token literal. Token is not shell-escaped into
    # the script body because we write it via environment instead — the script
    # just echoes $UPSTREAM_TOKEN.
    script.write_text('#!/bin/sh\nprintf "%s" "$UPSTREAM_TOKEN"\n')
    script.chmod(stat.S_IRWXU)  # rwx for owner only
    return script


def _run_git_clone(
    url: str, ref: str | None, dest: Path, *, token: str | None, username: str | None
) -> None:
    """Clone ``url`` into ``dest`` (must not exist). Raises UpstreamError on failure.

    The token, if any, is passed via GIT_ASKPASS so it never appears in
    process args, the URL, or stdout/stderr. The username is injected into
    the URL host segment since git's HTTP auth expects ``user@host`` for the
    prompt user to match.
    """
    clone_url = url
    if token and username:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            # Rebuild the URL with the username. Leaving the password out lets
            # GIT_ASKPASS supply it from the env without it ever being logged.
            netloc = f"{username}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            clone_url = parsed._replace(netloc=netloc).geturl()

    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [clone_url, str(dest)]

    env = os.environ.copy()
    tmpdir = Path(tempfile.mkdtemp(prefix="upstream-askpass-"))
    try:
        if token:
            askpass = _write_askpass_script(token, tmpdir)
            env["GIT_ASKPASS"] = str(askpass)
            env["UPSTREAM_TOKEN"] = token
            # Don't fall back to the terminal if the token is rejected.
            env["GIT_TERMINAL_PROMPT"] = "0"

        logger.info("git clone %s -> %s (ref=%s, token=%s)",
                    _redact_url(url), dest, ref, "yes" if token else "no")
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            stderr = _scrub_token_from_text(result.stderr, token)
            raise UpstreamError(
                f"git clone failed (exit {result.returncode}): {stderr.strip()}"
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _git_rev_parse_head(repo_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except FileNotFoundError:
        return None
    return None


def _redact_url(url: str) -> str:
    """Return a URL safe to log — strips any userinfo."""
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        return parsed._replace(netloc=host).geturl()
    return url


def _scrub_token_from_text(text: str, token: str | None) -> str:
    if not token:
        return text
    return text.replace(token, "<redacted>")


def _apply_subpath(repo_dir: Path, subpath: str) -> None:
    """Move ``repo_dir/subpath`` contents up to repo_dir, dropping everything else.

    Done via a sibling temp rename so we don't have to worry about name
    collisions between subpath contents and other files at the repo root.
    """
    norm = subpath.strip("/").strip()
    if not norm:
        return
    src = (repo_dir / norm).resolve()
    if not src.is_relative_to(repo_dir.resolve()):
        raise UpstreamError(f"subpath '{subpath}' escapes the repository")
    if not src.is_dir():
        raise UpstreamError(f"subpath '{subpath}' not found in the repository")

    staged = repo_dir.parent / (repo_dir.name + ".subpath")
    shutil.move(str(src), str(staged))
    shutil.rmtree(repo_dir)
    staged.rename(repo_dir)


def _flatten_single_wrapper_dir(repo_dir: Path) -> None:
    """If the repo root has exactly one child directory and no files, lift it.

    Mirrors the same flatten that upload.py applies to uploaded source trees.
    """
    children = [c for c in repo_dir.iterdir() if c.name != ".git"]
    if len(children) != 1 or not children[0].is_dir():
        return
    wrapper = children[0]
    staged = repo_dir.parent / (repo_dir.name + ".flatten")
    shutil.move(str(wrapper), str(staged))
    # Preserve .git so last_synced_sha can still be read.
    git_dir = repo_dir / ".git"
    if git_dir.exists():
        shutil.move(str(git_dir), str(staged / ".git"))
    shutil.rmtree(repo_dir)
    staged.rename(repo_dir)


def fetch_upstream(manuscript, source_dir: Path) -> str | None:
    """Clone the manuscript's upstream into source_dir, replacing its contents.

    Returns the cloned HEAD SHA (or None if git rev-parse failed). Raises
    UpstreamError on any user-visible failure — caller is responsible for
    surfacing the message.
    """
    url = manuscript.upstream_url
    if not url:
        raise UpstreamError("Manuscript has no upstream_url set")
    if is_upload_url(url):
        raise UpstreamError(
            "Manuscript source was uploaded directly; there is nothing to sync."
        )

    token: str | None = None
    if manuscript.upstream_token_encrypted:
        token = decrypt_token(manuscript.upstream_token_encrypted)
    username = derive_git_username(url) if token else None

    parent = source_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Clone into a sibling tempdir so we can atomically swap at the end.
    staging = Path(tempfile.mkdtemp(prefix="upstream-clone-", dir=parent))
    clone_target = staging / "repo"
    try:
        _run_git_clone(
            url, manuscript.upstream_ref, clone_target,
            token=token, username=username,
        )
        if manuscript.upstream_subpath:
            _apply_subpath(clone_target, manuscript.upstream_subpath)
        else:
            _flatten_single_wrapper_dir(clone_target)

        sha = _git_rev_parse_head(clone_target)

        # Drop .git to keep source_dir lean — nothing in the pipeline needs it
        # and it would bloat backups.
        git_dir = clone_target / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)

        # Atomic-ish swap. shutil.rmtree on a live dir isn't strictly atomic,
        # but the clone has already succeeded so we're past the risky part.
        if source_dir.exists():
            shutil.rmtree(source_dir)
        shutil.move(str(clone_target), str(source_dir))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return sha
