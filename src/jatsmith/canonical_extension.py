"""Fetch and manage the journal's canonical class file & Quarto extension.

The journal's canonical sources are configured in SiteConfig as two optional
fields:

- ``class_file_url`` — direct URL to the LaTeX class file (e.g. ``ccr.cls``).
  Accepts both GitHub HTML URLs (``github.com/<o>/<r>/blob/<ref>/<path>``)
  and raw URLs (``raw.githubusercontent.com/...``); HTML URLs are normalized
  to raw automatically.
- ``quarto_extension_repo`` — ``<owner>/<repo>[@<ref>]`` shorthand matching
  Quarto's own ``quarto add`` argument. We download the repo's tarball,
  extract its ``_extensions/`` subtree into the cache, and discover
  extension roots by ``_extension.yml`` markers (same heuristic Quarto uses).

Either or both may be empty. Empty disables drift detection and the
"use latest class file" toggle for that part.

Lifecycle:
- ``fetch_canonical_bundle(cfg, cache_dir)`` is called from the FastAPI
  lifespan handler on startup and again when SiteConfig URLs change. Result
  is stored on disk under ``cache_dir`` (default ``STORAGE_DIR/canonical/``)
  and in a module-level cache exposed via ``get_current_bundle()``.
- The pipeline reads ``get_current_bundle()`` and threads paths into
  ``install_canonical_class_file`` / ``install_canonical_extension`` and
  ``warn_if_outdated``. The CLI loads from ``cache_dir`` directly via
  ``load_cached_bundle`` — no fetching.

This module replaces the old CCR-specific ``ccr_cls.py``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# LaTeX convention: ``\ProvidesClass{name}[<release info>]``. The optional
# bracket argument carries whatever the class author chose to put there —
# typically ``YYYY-MM-DD vX.YY`` plus an optional description. We treat the
# whole bracket as an opaque "version string" for display and drift checks.
_PROVIDES_CLASS_RE = re.compile(
    r"\\ProvidesClass\s*\{[^}]*\}\s*\[([^\]]*)\]",
)
_EXTENSIONS_SUBDIR = "extensions"  # cache_dir/extensions/<sub>


# ---------------------------------------------------------------------------
# Bundle dataclass + module cache
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalBundle:
    """A snapshot of what's currently cached on disk for the canonical sources.

    Created by :func:`fetch_canonical_bundle` (after a fetch attempt) and by
    :func:`load_cached_bundle` (without fetching). All paths are absolute.
    Empty fields signal that the corresponding feature isn't configured or
    isn't cached yet.
    """
    cache_dir: Path
    # Class file
    class_filename: str | None = None        # basename(class_file_url) or None
    class_file_path: Path | None = None      # cache_dir / class_filename if cached
    class_version: str | None = None         # ProvidesClass optional argument
    class_sha: str | None = None             # sha256 of cached class file
    # Quarto extension(s)
    extensions_dir: Path | None = None       # cache_dir / "extensions" if cached
    extension_subpaths: tuple[str, ...] = ()  # rel paths of _extension.yml dirs
    extension_sha: str | None = None         # aggregate sha256 of cached bundle
    extension_version: str | None = None     # version: key from first _extension.yml

    @property
    def has_class_file(self) -> bool:
        return self.class_file_path is not None and self.class_file_path.is_file()

    @property
    def has_extensions(self) -> bool:
        return bool(self.extension_subpaths) and self.extensions_dir is not None

    @property
    def is_configured(self) -> bool:
        """True if any URL is configured (regardless of whether fetch succeeded)."""
        return self.class_filename is not None or self.has_extensions


_current_bundle: CanonicalBundle | None = None


def get_current_bundle() -> CanonicalBundle | None:
    """Return the bundle most recently set by the lifespan handler."""
    return _current_bundle


def set_current_bundle(bundle: CanonicalBundle | None) -> None:
    global _current_bundle
    _current_bundle = bundle


# ---------------------------------------------------------------------------
# Hash & version helpers
# ---------------------------------------------------------------------------


_EXTENSION_VERSION_RE = re.compile(
    r'^\s*version\s*:\s*"?([^"\s#]+)"?\s*(?:#.*)?$',
)


def parse_extension_version(yml_path: Path) -> str | None:
    """Extract the ``version:`` value from a Quarto ``_extension.yml`` file.

    Tries PyYAML first; falls back to a small line-based parser so the CLI
    works without the optional yaml dependency. Returns the value as a
    string (e.g. ``"0.08"``) or None if the file is missing/unparseable or
    has no ``version`` key.
    """
    try:
        text = yml_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if isinstance(data, dict) and data.get("version") is not None:
            return str(data["version"])
    except ImportError:
        pass
    for line in text.splitlines():
        m = _EXTENSION_VERSION_RE.match(line)
        if m:
            return m.group(1)
    return None


def parse_class_version(cls_path: Path) -> str | None:
    """Return the ``\\ProvidesClass`` optional argument as a free-text string.

    The LaTeX ``\\ProvidesClass{<name>}[<release info>]`` convention is the
    source of truth: ``<release info>`` is whatever the class author put in
    the brackets — typically ``YYYY-MM-DD vX.YY [description]``. Returns the
    bracket content (whitespace-trimmed) or ``None`` if the file has no
    ``\\ProvidesClass`` with an optional argument.
    """
    try:
        text = cls_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _PROVIDES_CLASS_RE.search(text)
    if not m:
        return None
    return m.group(1).strip() or None


def compute_class_sha256(cls_path: Path) -> str:
    """SHA-256 of ``cls_path`` with line endings normalized to ``\\n``."""
    text = cls_path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_extension_sha256(ext_dir: Path) -> str:
    """SHA-256 of an extension bundle (filenames + normalized contents).

    Walks ``ext_dir`` deterministically, hashing each file's path (relative,
    POSIX) and contents. Text files have CRLF normalized to LF so Windows
    checkouts don't drift from Unix ones. Binary files (e.g. logo PDFs)
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


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$"
)


def normalize_class_file_url(url: str) -> str:
    """Convert a GitHub ``blob/...`` HTML URL to its ``raw.githubusercontent.com``
    equivalent. Pass-through for raw URLs and non-GitHub URLs.
    """
    m = _GITHUB_BLOB_RE.match(url.strip())
    if not m:
        return url.strip()
    owner, repo, ref, path = m.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


_QUARTO_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:@(.+))?$")


def parse_quarto_repo(spec: str) -> tuple[str, str, str] | None:
    """Parse ``<owner>/<repo>[@<ref>]``. Returns ``(owner, repo, ref)`` or
    ``None`` if the spec is malformed. Default ref is ``main``.
    """
    spec = spec.strip()
    if not spec:
        return None
    m = _QUARTO_REPO_RE.match(spec)
    if not m:
        return None
    owner, repo, ref = m.groups()
    return owner, repo, (ref or "main")


# ---------------------------------------------------------------------------
# Fetch helpers (HTTP + tarball)
# ---------------------------------------------------------------------------


def _http_get(url: str, *, timeout: float) -> bytes:
    """GET ``url`` and return the body. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "jatsmith"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _fetch_class_file(
    url: str, dest_dir: Path, *, timeout: float,
) -> Path | None:
    """Fetch the class file at ``url`` into ``dest_dir/<basename>``.

    URL is normalized (HTML→raw) before fetch. Returns the destination path
    on success. On failure, logs a warning and leaves any prior cached copy
    untouched (returns the existing cached path if present, else None).
    """
    raw_url = normalize_class_file_url(url)
    filename = os.path.basename(raw_url.split("?", 1)[0])
    if not filename:
        logger.warning("class_file_url has no filename component: %s", url)
        return None
    dest = dest_dir / filename
    try:
        body = _http_get(raw_url, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.warning(
            "Failed to fetch class file from %s: %s. "
            "Falling back to cached copy.", raw_url, exc,
        )
        return dest if dest.is_file() else None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    logger.info("Fetched canonical class file %s (%d bytes)", filename, len(body))
    return dest


def _fetch_quarto_extension(
    spec: str, cache_dir: Path, *, timeout: float,
) -> Path | None:
    """Download the Quarto extension repo's tarball and extract its
    ``_extensions/`` subtree into ``cache_dir/extensions/``.

    ``spec`` is the ``<owner>/<repo>[@<ref>]`` SiteConfig value. On HTTP or
    extraction failure, logs a warning and leaves the existing
    ``cache_dir/extensions/`` (if any) untouched. Returns the
    ``extensions/`` directory path if it exists after the call (regardless
    of whether this fetch wrote it), else None.
    """
    parsed = parse_quarto_repo(spec)
    extensions_dir = cache_dir / _EXTENSIONS_SUBDIR
    if parsed is None:
        logger.warning(
            "quarto_extension_repo %r is malformed (expected '<owner>/<repo>[@<ref>]'); "
            "skipping fetch.", spec,
        )
        return extensions_dir if extensions_dir.is_dir() else None
    owner, repo, ref = parsed
    archive_url = f"https://github.com/{owner}/{repo}/archive/{ref}.tar.gz"

    try:
        body = _http_get(archive_url, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.warning(
            "Failed to fetch Quarto extension tarball from %s: %s. "
            "Falling back to cached copy.", archive_url, exc,
        )
        return extensions_dir if extensions_dir.is_dir() else None

    # Extract _extensions/* into a staging dir, then atomically swap.
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="canonical-ext-", dir=cache_dir) as tmp:
        staging = Path(tmp) / "extensions"
        staging.mkdir(parents=True)
        try:
            with tarfile.open(fileobj=_io_BytesIO(body), mode="r:gz") as tf:
                _extract_extensions_subtree(tf, staging)
        except (tarfile.TarError, OSError) as exc:
            logger.warning(
                "Failed to extract Quarto extension tarball from %s: %s.",
                archive_url, exc,
            )
            return extensions_dir if extensions_dir.is_dir() else None

        if not any(staging.rglob("*")):
            logger.warning(
                "Quarto extension repo %s/%s@%s has no _extensions/ tree; "
                "leaving prior cache untouched.", owner, repo, ref,
            )
            return extensions_dir if extensions_dir.is_dir() else None

        # Swap: rmtree old, move staging into place.
        if extensions_dir.is_dir():
            shutil.rmtree(extensions_dir)
        shutil.move(str(staging), str(extensions_dir))

    n_files = sum(1 for _ in extensions_dir.rglob("*") if _.is_file())
    logger.info(
        "Fetched canonical Quarto extension %s/%s@%s (%d files)",
        owner, repo, ref, n_files,
    )
    return extensions_dir


def _io_BytesIO(data: bytes):
    """Lazy import to keep top-level imports minimal."""
    import io
    return io.BytesIO(data)


def _extract_extensions_subtree(tf: tarfile.TarFile, dest: Path) -> None:
    """Extract ``<repo-ref>/_extensions/...`` members of ``tf`` into ``dest``.

    Members outside ``_extensions/`` are skipped. Members with ``..`` or
    absolute paths are rejected.
    """
    for member in tf.getmembers():
        # GitHub tarballs wrap content in a single top-level dir like
        # ``ccr-quarto-main/``. Strip it, then look for ``_extensions/...``.
        parts = Path(member.name).parts
        if len(parts) < 2 or parts[1] != "_extensions":
            continue
        rel_parts = parts[2:]  # strip <repo-ref>/_extensions/
        if not rel_parts:
            continue
        # Reject any traversal or absolute components.
        if any(p in ("..", "") or p.startswith("/") for p in rel_parts):
            logger.warning("Skipping suspicious tar member: %s", member.name)
            continue
        target = dest.joinpath(*rel_parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            continue  # symlinks / device nodes — skip
        target.parent.mkdir(parents=True, exist_ok=True)
        f = tf.extractfile(member)
        if f is None:
            continue
        target.write_bytes(f.read())


# ---------------------------------------------------------------------------
# Bundle loading + fetching
# ---------------------------------------------------------------------------


def discover_extension_subpaths(extensions_dir: Path) -> list[str]:
    """Return the relative paths of every extension root under ``extensions_dir``.

    A directory is an "extension root" if it contains an ``_extension.yml``
    file. Mirrors how Quarto itself locates extensions inside a project's
    ``_extensions/`` tree.
    """
    if not extensions_dir.is_dir():
        return []
    roots: list[str] = []
    for marker in extensions_dir.rglob("_extension.yml"):
        rel = marker.parent.relative_to(extensions_dir).as_posix()
        if rel == ".":
            continue  # _extension.yml at extensions_dir root would be unusual
        roots.append(rel)
    return sorted(roots)


def load_cached_bundle(cache_dir: Path, class_file_url: str) -> CanonicalBundle:
    """Build a CanonicalBundle from whatever's currently in ``cache_dir``.

    Doesn't fetch. Used by the CLI (which has no fetch loop) and by the
    web service after a fetch attempt to capture the post-fetch state.
    """
    class_filename: str | None = None
    class_file_path: Path | None = None
    class_version: str | None = None
    class_sha: str | None = None

    if class_file_url.strip():
        raw_url = normalize_class_file_url(class_file_url)
        class_filename = os.path.basename(raw_url.split("?", 1)[0]) or None
        if class_filename:
            candidate = cache_dir / class_filename
            if candidate.is_file():
                class_file_path = candidate
                class_version = parse_class_version(candidate)
                class_sha = compute_class_sha256(candidate)

    extensions_dir = cache_dir / _EXTENSIONS_SUBDIR
    extension_subpaths: tuple[str, ...] = ()
    extension_sha: str | None = None
    extension_version: str | None = None
    if extensions_dir.is_dir():
        extension_subpaths = tuple(discover_extension_subpaths(extensions_dir))
        if extension_subpaths:
            extension_sha = compute_extension_sha256(extensions_dir)
            extension_version = parse_extension_version(
                extensions_dir / extension_subpaths[0] / "_extension.yml"
            )
        else:
            extensions_dir = None  # empty / no markers — treat as not cached

    return CanonicalBundle(
        cache_dir=cache_dir,
        class_filename=class_filename,
        class_file_path=class_file_path,
        class_version=class_version,
        class_sha=class_sha,
        extensions_dir=extensions_dir,
        extension_subpaths=extension_subpaths,
        extension_sha=extension_sha,
        extension_version=extension_version,
    )


def load_bundle_from_storage_dir() -> CanonicalBundle | None:
    """Build a CanonicalBundle from ``STORAGE_DIR/canonical/`` using the URL
    in the local SQLite DB (so the CLI sees the same canonical bundle the
    web service has cached). Returns None if STORAGE_DIR is unset, the cache
    dir doesn't exist, or the SiteConfig row hasn't been seeded yet.

    Used by the standalone CLI (``uv run jatsmith ...``) — the web service
    populates the bundle in the lifespan handler instead.
    """
    storage_dir = os.environ.get("STORAGE_DIR")
    if not storage_dir:
        return None
    cache_dir = Path(storage_dir) / "canonical"
    if not cache_dir.is_dir():
        return None
    # Read class_file_url from the SiteConfig row (so the cached basename
    # resolves correctly). load_site_config knows how to do this without
    # SQLAlchemy.
    from jatsmith.site_config import load_site_config
    cfg = load_site_config()
    return load_cached_bundle(cache_dir, cfg.class_file_url)


def fetch_canonical_bundle(
    class_file_url: str,
    quarto_extension_repo: str,
    cache_dir: Path,
    *,
    timeout: float = 15.0,
) -> CanonicalBundle:
    """Fetch the canonical bundle into ``cache_dir`` and return a snapshot.

    Network failures are caught and logged — a failed fetch falls back to
    whatever's already cached, so the app never blocks startup on a
    transient network blip. If neither URL is configured, this is a no-op
    and returns the empty bundle for ``cache_dir``.

    Either argument may be blank; that part is simply skipped.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    if class_file_url.strip():
        _fetch_class_file(class_file_url, cache_dir, timeout=timeout)

    if quarto_extension_repo.strip():
        _fetch_quarto_extension(quarto_extension_repo, cache_dir, timeout=timeout)

    return load_cached_bundle(cache_dir, class_file_url)


# ---------------------------------------------------------------------------
# Workspace ops (find / install)
# ---------------------------------------------------------------------------


def find_class_file_in_workspace(
    workspace_dir: Path, class_filename: str,
) -> Path | None:
    """Locate the primary class file in a workspace.

    Looks for ``<class_filename>`` at the workspace root first, then under
    ``_extensions/*/<class_filename>``. Returns the first match, or None.
    """
    return next(iter(find_class_files_in_workspace(workspace_dir, class_filename)), None)


def find_class_files_in_workspace(
    workspace_dir: Path, class_filename: str,
) -> list[Path]:
    """Return every copy of ``class_filename`` in a workspace, in priority
    order (flat root first, then any nested copies under ``_extensions/``).
    """
    out: list[Path] = []
    flat = workspace_dir / class_filename
    if flat.is_file():
        out.append(flat)
    ext_root = workspace_dir / "_extensions"
    if ext_root.is_dir():
        for nested in sorted(ext_root.rglob(class_filename)):
            if nested.is_file() and nested != flat:
                out.append(nested)
    return out


def install_canonical_class_file(
    workspace_dir: Path, cached_class_file: Path, class_filename: str,
) -> Path | None:
    """Overwrite every workspace copy of the class file with the cached one.

    If no copy exists, writes one to ``workspace_dir/<class_filename>``.
    Returns the first path written. Returns None if the cached file does
    not exist (caller should have checked, but we no-op safely).
    """
    if not cached_class_file.is_file():
        logger.warning(
            "install_canonical_class_file: %s is not a file; skipping",
            cached_class_file,
        )
        return None
    targets = find_class_files_in_workspace(workspace_dir, class_filename)
    if not targets:
        targets = [workspace_dir / class_filename]
    version = parse_class_version(cached_class_file)
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached_class_file, target)
        logger.info(
            "Installed canonical %s%s at %s",
            class_filename,
            f" [{version}]" if version else "",
            target,
        )
    return targets[0]


def find_extension_in_workspace(
    workspace_dir: Path, rel_subpath: str,
) -> Path | None:
    """Return ``workspace_dir/_extensions/<rel_subpath>`` if it exists, else None."""
    ext_dir = workspace_dir / "_extensions" / rel_subpath
    return ext_dir if ext_dir.is_dir() else None


def install_canonical_extensions(
    workspace_dir: Path, bundle: CanonicalBundle,
) -> list[Path]:
    """Sync each cached extension subdir into the workspace's _extensions/.

    Each ``<extensions_dir>/<sub>`` is copied to
    ``<workspace_dir>/_extensions/<sub>``, replacing any existing copy. Other
    workspace ``_extensions/`` entries (third-party extensions the author may
    use) are left untouched.

    Returns the list of paths written. If the bundle has no extensions
    cached, returns an empty list.
    """
    if not bundle.has_extensions or bundle.extensions_dir is None:
        return []
    written: list[Path] = []
    for sub in bundle.extension_subpaths:
        src = bundle.extensions_dir / sub
        if not src.is_dir():
            continue
        dest = workspace_dir / "_extensions" / sub
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        logger.info("Installed canonical extension %s at %s", sub, dest)
        written.append(dest)

    # Also sync a flat workspace-root copy of the class file if present and
    # the bundle has one — keeps mixed layouts (Quarto + flat .cls in the
    # same workspace) consistent.
    if bundle.has_class_file and bundle.class_filename:
        flat = workspace_dir / bundle.class_filename
        if flat.is_file():
            shutil.copyfile(bundle.class_file_path, flat)
            logger.info(
                "Installed canonical %s at %s (flat copy)",
                bundle.class_filename, flat,
            )
            written.append(flat)
    return written


# ---------------------------------------------------------------------------
# Drift detection (warnings)
# ---------------------------------------------------------------------------


def warn_if_outdated(
    workspace_dir: Path, bundle: CanonicalBundle | None = None,
) -> None:
    """Warn if the workspace's class file or vendored extension drifts from
    the canonical copy.

    No-ops when the bundle is None or empty (e.g. the deployer hasn't
    configured URLs, or the fetch hasn't run yet).
    """
    if bundle is None:
        bundle = get_current_bundle()
    if bundle is None or not bundle.is_configured:
        return

    # Class file drift
    if bundle.has_class_file and bundle.class_filename:
        cls = find_class_file_in_workspace(workspace_dir, bundle.class_filename)
        if cls is not None:
            _warn_if_class_drifts(cls, bundle)

    # Extension bundle drift
    if bundle.has_extensions and bundle.extensions_dir is not None:
        _warn_if_extensions_drift(workspace_dir, bundle)


def _warn_if_class_drifts(cls_path: Path, bundle: CanonicalBundle) -> None:
    """Compare the workspace class file against the cached canonical copy.

    Drift is determined by SHA — semantic version comparison would require
    parsing whatever shape the ``\\ProvidesClass`` optional argument takes,
    which varies between journals. When the SHAs differ we include both
    ``\\ProvidesClass`` strings in the warning so the editor can see at a
    glance whether the workspace copy is older, newer, or just edited.
    """
    if bundle.class_sha is None:
        return  # no canonical hash to compare against
    workspace_sha = compute_class_sha256(cls_path)
    if workspace_sha == bundle.class_sha:
        return  # in sync

    workspace_version = parse_class_version(cls_path)
    canonical_version = bundle.class_version
    if (
        workspace_version
        and canonical_version
        and workspace_version != canonical_version
    ):
        logger.warning(
            "%s identifies as %r but the canonical copy is %r. "
            "Turn on \"Use latest class file\" or replace your copy with the "
            "canonical version.",
            bundle.class_filename, workspace_version, canonical_version,
        )
    else:
        logger.warning(
            "%s does not match the canonical upstream copy "
            "(sha256=%s, expected=%s); it may have been edited. "
            "Keep layout customizations in the document, not the class file.",
            bundle.class_filename, workspace_sha, bundle.class_sha,
        )


def _warn_if_extensions_drift(
    workspace_dir: Path, bundle: CanonicalBundle,
) -> None:
    assert bundle.extensions_dir is not None  # checked by caller
    # Build a workspace-side directory tree limited to the canonical subpaths,
    # so unrelated third-party extensions don't poison the hash.
    workspace_ext_root = workspace_dir / "_extensions"
    if not workspace_ext_root.is_dir():
        return
    relevant: list[tuple[str, Path]] = []
    for sub in bundle.extension_subpaths:
        ws_dir = workspace_ext_root / sub
        if ws_dir.is_dir():
            relevant.append((sub, ws_dir))
    if not relevant:
        return  # author hasn't vendored these extensions; nothing to compare

    # Hash workspace-side and canonical-side using the same logic, restricted
    # to the union of subpaths that exist in both.
    def _hash_subset(root: Path, subs: list[str]) -> str:
        h = hashlib.sha256()
        for sub in subs:
            sub_root = root / sub
            for p in sorted(sub_root.rglob("*")):
                if not p.is_file():
                    continue
                rel = (Path(sub) / p.relative_to(sub_root)).as_posix()
                h.update(rel.encode("utf-8"))
                h.update(b"\0")
                try:
                    text = p.read_text(encoding="utf-8")
                    h.update(text.replace("\r\n", "\n").encode("utf-8"))
                except UnicodeDecodeError:
                    h.update(p.read_bytes())
                h.update(b"\0")
        return h.hexdigest()

    subs_in_ws = [sub for sub, _ in relevant]
    workspace_sha = _hash_subset(workspace_ext_root, subs_in_ws)
    canonical_sha = _hash_subset(bundle.extensions_dir, subs_in_ws)
    if workspace_sha == canonical_sha:
        return
    logger.warning(
        "Vendored Quarto extension(s) %s differ from the canonical bundle "
        "(workspace sha256=%s, canonical=%s); refresh with `quarto add %s` "
        "or turn on \"Use latest class file\" to overwrite.",
        ", ".join(subs_in_ws), workspace_sha, canonical_sha,
        # The bundle doesn't carry the original spec; reconstruct as a hint.
        subs_in_ws[0] if subs_in_ws else "<repo>",
    )
