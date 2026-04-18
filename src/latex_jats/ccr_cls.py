"""Detect outdated or edited copies of the CCR class (``ccr.cls``).

Upstream lives at https://github.com/ccr-journal/ccr-latex. Authors vendor a
copy of ``ccr.cls`` alongside their LaTeX source or inside a Quarto extension
at ``_extensions/ccr-journal/ccr/ccr.cls``. Those copies drift: sometimes the
author is simply behind (older version), sometimes they have edited the class
to tweak layout (same version, different content).

Two pinned constants describe what "current" means:

- ``EXPECTED_CCR_CLS_VERSION`` — the ``% Version X.XX`` comment of the latest
  upstream release.
- ``EXPECTED_CCR_CLS_SHA256`` — SHA-256 of that same file, after normalizing
  line endings to ``\\n`` (so Windows CRLF authors don't trip false alarms).

When upstream releases a new version, bump both constants (and the expected
hash in ``tests/test_ccr_cls.py``). To recompute the checksum for the new
file::

    uv run python -c "from latex_jats.ccr_cls import compute_ccr_cls_sha256; \\
        import pathlib; print(compute_ccr_cls_sha256(pathlib.Path('ccr.cls')))"
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


EXPECTED_CCR_CLS_VERSION = "0.05"
EXPECTED_CCR_CLS_SHA256 = "d71fd2c8d572dab83e4afff2058618afe9c746289623468168ff3bdb50e01387"

_VERSION_RE = re.compile(r"^\s*%\s*Version\s+(\d+(?:\.\d+)+)", re.IGNORECASE)


def find_ccr_cls(workspace_dir: Path) -> Path | None:
    """Locate ``ccr.cls`` in a prepared workspace.

    Checks the flat LaTeX layout first, then the Quarto extension layout.
    Returns ``None`` if neither exists.
    """
    candidates = [
        workspace_dir / "ccr.cls",
        workspace_dir / "_extensions" / "ccr-journal" / "ccr" / "ccr.cls",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse_ccr_cls_version(cls_path: Path) -> str | None:
    """Return the ``X.XX`` version from the ``% Version`` comment, or ``None``."""
    with cls_path.open(encoding="utf-8", errors="replace") as f:
        for _, line in zip(range(10), f):
            m = _VERSION_RE.match(line)
            if m:
                return m.group(1)
    return None


def compute_ccr_cls_sha256(cls_path: Path) -> str:
    """SHA-256 of ``cls_path`` with line endings normalized to ``\\n``."""
    text = cls_path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def warn_if_outdated(workspace_dir: Path) -> None:
    """Warn if the vendored ``ccr.cls`` is older than or differs from upstream.

    - Missing ``ccr.cls`` → silent (not every submission uses it).
    - Missing/malformed ``% Version`` comment → info log, no warning.
    - Older version → warning with upgrade guidance.
    - Newer version → silent (author is ahead of us).
    - Matching version but different hash → softer "may have been edited"
      warning. Not fatal: authors sometimes have valid reasons (recent
      upstream fix we haven't synced, benign whitespace), but layout tweaks
      to the class file are almost always wrong and worth flagging.
    """
    cls = find_ccr_cls(workspace_dir)
    if cls is None:
        return

    version = parse_ccr_cls_version(cls)
    if version is None:
        logger.info(
            "%s has no '%% Version X.XX' comment; skipping CCR class version check",
            cls,
        )
        return

    try:
        local = _version_tuple(version)
        expected = _version_tuple(EXPECTED_CCR_CLS_VERSION)
    except ValueError:
        logger.info(
            "%s has unparseable version %r; skipping CCR class version check",
            cls, version,
        )
        return

    if local < expected:
        logger.warning(
            "ccr.cls is v%s but the latest release is v%s. "
            "Please upgrade: for Quarto, re-run `quarto add ccr-journal/ccr-latex`; "
            "for LaTeX, replace ccr.cls with the copy from "
            "https://github.com/ccr-journal/ccr-latex.",
            version, EXPECTED_CCR_CLS_VERSION,
        )
        return

    if local > expected:
        return

    sha = compute_ccr_cls_sha256(cls)
    if sha != EXPECTED_CCR_CLS_SHA256:
        logger.warning(
            "ccr.cls claims v%s but its contents do not match the canonical "
            "upstream copy (sha256=%s, expected=%s); it may have been edited. "
            "Please keep layout customizations in the document, not the class "
            "file, and restore the canonical ccr.cls from "
            "https://github.com/ccr-journal/ccr-latex.",
            version, sha, EXPECTED_CCR_CLS_SHA256,
        )
