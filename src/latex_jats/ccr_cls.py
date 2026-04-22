"""Detect outdated or edited copies of the CCR Quarto extension (which
includes ``ccr.cls``) and install a canonical copy on demand.

The Quarto extension at https://github.com/ccr-journal/ccr-quarto ships a
bundle of infrastructure files — ``ccr.cls``, ``ccrtemplate.tex``,
``ccr.lua``, partials, ``_extension.yml`` — that together define CCR's
house style. Authors vendor the bundle under
``_extensions/ccr-journal/ccr/`` (Quarto) or keep a flat ``ccr.cls`` next
to their LaTeX source. All files in the bundle are publishing-toolchain
infrastructure, not author content; customizations belong in the document.

What "current" means is derived at import time from the canonical bundle
committed at ``ccr_canonical_extension/``:

- ``EXPECTED_CCR_CLS_VERSION`` — the ``% Version X.XX`` comment in
  ``ccr.cls``.
- ``EXPECTED_CCR_CLS_SHA256`` — SHA-256 of ``ccr.cls`` after normalizing
  line endings to ``\\n`` (so Windows CRLF authors don't trip false alarms).
- ``EXPECTED_EXTENSION_SHA256`` — SHA-256 of the whole bundle (filenames +
  normalized contents, deterministically ordered).

When upstream releases a new version, replace files under
``ccr_canonical_extension/`` with the new upstream bundle; the pins update
automatically.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


CANONICAL_EXTENSION_DIR = Path(__file__).parent / "ccr_canonical_extension"
CANONICAL_CCR_CLS_PATH = CANONICAL_EXTENSION_DIR / "ccr.cls"

_VERSION_RE = re.compile(r"^\s*%\s*Version\s+(\d+(?:\.\d+)+)", re.IGNORECASE)

# Subdirectory inside a workspace where the CCR Quarto extension lives. This
# path is set by ``quarto add`` and the author is not expected to change it.
_EXTENSION_SUBPATH = Path("_extensions") / "ccr-journal" / "ccr"


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


def compute_extension_sha256(ext_dir: Path) -> str:
    """SHA-256 of an extension bundle (filenames + normalized contents).

    Walks ``ext_dir`` deterministically, hashing each file's path (relative,
    POSIX) and contents. Text files have CRLF normalized to LF so Windows
    checkouts don't drift from Unix ones. Binary files (e.g. aup_logo.pdf)
    pass through unchanged.
    """
    h = hashlib.sha256()
    for path in sorted(ext_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ext_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            text = path.read_text(encoding="utf-8")
            h.update(text.replace("\r\n", "\n").encode("utf-8"))
        except UnicodeDecodeError:
            h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _derive_expected_version() -> str:
    v = parse_ccr_cls_version(CANONICAL_CCR_CLS_PATH)
    if v is None:
        raise RuntimeError(
            f"{CANONICAL_CCR_CLS_PATH} has no '% Version X.XX' comment; "
            "the canonical ccr.cls must be version-stamped."
        )
    return v


EXPECTED_CCR_CLS_VERSION = _derive_expected_version()
EXPECTED_CCR_CLS_SHA256 = compute_ccr_cls_sha256(CANONICAL_CCR_CLS_PATH)
EXPECTED_EXTENSION_SHA256 = compute_extension_sha256(CANONICAL_EXTENSION_DIR)


def install_canonical_ccr_cls(workspace_dir: Path) -> Path:
    """Overwrite every ``ccr.cls`` in the workspace with the canonical copy.

    Covers both layouts — flat workspace-root ``ccr.cls`` (LaTeX submissions)
    and ``_extensions/ccr-journal/ccr/ccr.cls`` (Quarto submissions). For
    Quarto, prefer ``install_canonical_ccr_extension`` to sync the whole
    bundle; this function is retained for the flat LaTeX path.

    If no existing copy is present, the canonical file is written to
    ``workspace_dir / ccr.cls``. Returns the first path written.
    """
    targets = find_ccr_cls_all(workspace_dir) or [workspace_dir / "ccr.cls"]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANONICAL_CCR_CLS_PATH, target)
        logger.info("Installed canonical ccr.cls v%s at %s",
                    EXPECTED_CCR_CLS_VERSION, target)
    return targets[0]


def install_canonical_ccr_extension(workspace_dir: Path) -> Path:
    """Overwrite the vendored CCR Quarto extension bundle with the canonical copy.

    Syncs the entire ``_extensions/ccr-journal/ccr/`` tree — ``ccr.cls``,
    ``ccrtemplate.tex``, ``ccr.lua``, ``_extension.yml``, partials, and any
    other bundled resources. An older vendored bundle (e.g. missing a
    template partial that the canonical class now expects) would cause PDF
    compilation to fail silently; sync-all avoids that class of bug.

    Also overwrites a flat workspace-root ``ccr.cls`` if one exists, so
    mixed layouts stay consistent. Returns the path of the extension root
    (``workspace_dir/_extensions/ccr-journal/ccr``).
    """
    ext_target = workspace_dir / _EXTENSION_SUBPATH
    if ext_target.exists():
        shutil.rmtree(ext_target)
    ext_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CANONICAL_EXTENSION_DIR, ext_target)
    logger.info("Installed canonical CCR Quarto extension (ccr.cls v%s) at %s",
                EXPECTED_CCR_CLS_VERSION, ext_target)

    flat_cls = workspace_dir / "ccr.cls"
    if flat_cls.is_file():
        shutil.copyfile(CANONICAL_CCR_CLS_PATH, flat_cls)
        logger.info("Installed canonical ccr.cls v%s at %s",
                    EXPECTED_CCR_CLS_VERSION, flat_cls)
    return ext_target


def find_ccr_cls(workspace_dir: Path) -> Path | None:
    """Locate the primary ``ccr.cls`` in a prepared workspace.

    Checks the flat LaTeX layout first, then the Quarto extension layout.
    Returns ``None`` if neither exists.
    """
    copies = find_ccr_cls_all(workspace_dir)
    return copies[0] if copies else None


def find_ccr_cls_all(workspace_dir: Path) -> list[Path]:
    """Return every ``ccr.cls`` copy in a prepared workspace, in priority order."""
    candidates = [
        workspace_dir / "ccr.cls",
        workspace_dir / _EXTENSION_SUBPATH / "ccr.cls",
    ]
    return [c for c in candidates if c.is_file()]


def find_ccr_extension(workspace_dir: Path) -> Path | None:
    """Return the vendored extension directory in a workspace, if present."""
    ext_dir = workspace_dir / _EXTENSION_SUBPATH
    return ext_dir if ext_dir.is_dir() else None


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def warn_if_outdated(workspace_dir: Path) -> None:
    """Warn if the vendored CCR class/extension drifts from the canonical copy.

    - Missing ``ccr.cls`` → silent (not every submission uses it).
    - Missing/malformed ``% Version`` comment → info log, no warning.
    - Older ``ccr.cls`` version → warning with upgrade guidance.
    - Newer ``ccr.cls`` version → silent (author is ahead of us).
    - Matching version but different ``ccr.cls`` hash → softer warning.
    - Additionally: if a Quarto extension is vendored and the bundle hash
      differs from the canonical bundle, warn. Catches cases where the cls
      is current but another file in the bundle is stale (e.g. outdated
      ``_extension.yml`` missing a newly-required template partial).
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
            "Please upgrade: for Quarto, re-run `quarto add ccr-journal/ccr-quarto`; "
            "for LaTeX, replace ccr.cls with the copy from "
            "https://github.com/ccr-journal/ccr-latex.",
            version, EXPECTED_CCR_CLS_VERSION,
        )
    elif local == expected:
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

    _warn_if_extension_drifts(workspace_dir)


def _warn_if_extension_drifts(workspace_dir: Path) -> None:
    ext_dir = find_ccr_extension(workspace_dir)
    if ext_dir is None:
        return
    sha = compute_extension_sha256(ext_dir)
    if sha == EXPECTED_EXTENSION_SHA256:
        return
    logger.warning(
        "CCR Quarto extension at %s differs from the canonical bundle "
        "(sha256=%s, expected=%s); it may be outdated or edited. Please "
        "re-run `quarto add ccr-journal/ccr-quarto` to refresh it, and "
        "keep customizations in the document rather than the extension files.",
        ext_dir, sha, EXPECTED_EXTENSION_SHA256,
    )
