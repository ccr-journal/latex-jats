"""Journal-identity config used by the conversion pipeline.

Defined as a plain frozen dataclass so the standalone CLI can load and use it
without pulling in the web service's SQLAlchemy stack. The web service worker
constructs ``SiteConfigData`` from the SQLModel ``SiteConfig`` row and passes
it into ``convert()``; the CLI calls ``load_site_config()`` which reads the
same SQLite DB if ``STORAGE_DIR`` is set, or falls back to ``DEFAULT_SITE_CONFIG``.

``DEFAULT_SITE_CONFIG`` is a placeholder profile ("My Journal Name", "1234-5678",
…). Real values come from the SiteConfig row in the DB, which the editor edits
via the in-app form. The seed in alembic migration 0012 mirrors these defaults;
``test_default_matches_migration_seed`` keeps them in sync.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteConfigData:
    journal_id: str
    journal_title: str
    issn_epub: str
    issn_ppub: str
    publisher_name: str
    publisher_loc: str
    copyright_holder: str
    copyright_statement: str
    license_type: str
    license_url: str
    license_text: str
    doi_prefix: str
    # Branding fields aren't used by the conversion pipeline (only by the web
    # UI), but they live on this dataclass so the SiteConfig row maps 1:1.
    site_name: str
    site_description: str
    header_branding: str


DEFAULT_SITE_CONFIG = SiteConfigData(
    journal_id="MYJOURNAL",
    journal_title="My Journal Name",
    issn_epub="1234-5678",
    issn_ppub="",
    publisher_name="My Publisher",
    publisher_loc="City",
    copyright_holder="The authors",
    copyright_statement="© The authors",
    license_type="open-access",
    license_url="https://creativecommons.org/licenses/by/4.0/",
    license_text=(
        "This is an open access article distributed under the CC BY 4.0 license"
    ),
    doi_prefix="10.0000/",
    site_name="My Journal JATSmith",
    site_description=(
        "Copy-editing tool for [Journal name](https://example.com). "
        "Authors and editors can upload LaTeX and Quarto sources, convert to "
        "JATS-XML, HTML and PDF, and check and approve the results."
    ),
    header_branding="My Journal",
)


_FIELDS = (
    "journal_id",
    "journal_title",
    "issn_epub",
    "issn_ppub",
    "publisher_name",
    "publisher_loc",
    "copyright_holder",
    "copyright_statement",
    "license_type",
    "license_url",
    "license_text",
    "doi_prefix",
    "site_name",
    "site_description",
    "header_branding",
)


def load_site_config() -> SiteConfigData:
    """Load journal config from STORAGE_DIR/jatsmith.db, else CCR defaults.

    The web service worker should construct ``SiteConfigData`` directly from a
    DB session and pass it into ``convert()``; this loader exists for the
    standalone CLI, which has no SQLAlchemy session.
    """
    storage_dir = os.environ.get("STORAGE_DIR")
    if not storage_dir:
        return DEFAULT_SITE_CONFIG
    db_path = Path(storage_dir) / "jatsmith.db"
    if not db_path.exists():
        return DEFAULT_SITE_CONFIG
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                f"SELECT {', '.join(_FIELDS)} FROM siteconfig WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        logger.warning(
            "siteconfig table missing in %s (%s); falling back to CCR defaults",
            db_path, exc,
        )
        return DEFAULT_SITE_CONFIG
    if row is None:
        return DEFAULT_SITE_CONFIG
    return SiteConfigData(**dict(zip(_FIELDS, row)))
