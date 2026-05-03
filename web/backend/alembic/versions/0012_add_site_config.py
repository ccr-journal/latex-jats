"""Add singleton site_config table with placeholder defaults (Issue #32).

Externalizes journal-identity values that used to live as constants in
src/jatsmith/convert.py. Seeds the row with placeholders ("My Journal Name",
"1234-5678", …) so a fresh JATSmith install prompts the editor to fill in
their journal's real values via the in-app form on first login.

Revision ID: 0012_add_site_config
Revises: 0011_add_approval_audit
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_add_site_config"
down_revision = "0011_add_approval_audit"
branch_labels = None
depends_on = None


# Placeholder defaults — kept in sync with DEFAULT_SITE_CONFIG in
# src/jatsmith/site_config.py (test_default_matches_migration_seed enforces).
_DEFAULT_SEED = {
    "id": 1,
    "journal_id": "MYJOURNAL",
    "journal_title": "My Journal Name",
    "issn_epub": "1234-5678",
    "issn_ppub": "",
    "publisher_name": "My Publisher",
    "publisher_loc": "City",
    "copyright_holder": "The authors",
    "copyright_statement": "© The authors",
    "license_type": "open-access",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "license_text": (
        "This is an open access article distributed under the CC BY 4.0 license"
    ),
    "doi_prefix": "10.0000/",
    "configured_at": None,
}


def upgrade() -> None:
    op.create_table(
        "siteconfig",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("journal_id", sa.String(), nullable=False),
        sa.Column("journal_title", sa.String(), nullable=False),
        sa.Column("issn_epub", sa.String(), nullable=False, server_default=""),
        sa.Column("issn_ppub", sa.String(), nullable=False, server_default=""),
        sa.Column("publisher_name", sa.String(), nullable=False),
        sa.Column("publisher_loc", sa.String(), nullable=False),
        sa.Column("copyright_holder", sa.String(), nullable=False),
        sa.Column("copyright_statement", sa.String(), nullable=False),
        sa.Column("license_type", sa.String(), nullable=False, server_default="open-access"),
        sa.Column("license_url", sa.String(), nullable=False),
        sa.Column("license_text", sa.String(), nullable=False),
        sa.Column("doi_prefix", sa.String(), nullable=False),
        sa.Column("configured_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    bind = op.get_bind()
    cols = ", ".join(_DEFAULT_SEED.keys()) + ", updated_at"
    placeholders = ", ".join(f":{k}" for k in _DEFAULT_SEED.keys()) + ", CURRENT_TIMESTAMP"
    bind.execute(
        sa.text(f"INSERT INTO siteconfig ({cols}) VALUES ({placeholders})"),
        _DEFAULT_SEED,
    )


def downgrade() -> None:
    op.drop_table("siteconfig")
