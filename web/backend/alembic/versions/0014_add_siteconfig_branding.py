"""Add branding columns to siteconfig (Issue #32, action point 6).

site_name, site_description (markdown), and header_branding control the
journal-specific text on the landing page and in the header strap.

Revision ID: 0014_add_siteconfig_branding
Revises: 0013_drop_siteconfig_ojs_cols
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_add_siteconfig_branding"
down_revision = "0013_drop_siteconfig_ojs_cols"
branch_labels = None
depends_on = None


_DEFAULTS = {
    "site_name": "My Journal JATSmith",
    "site_description": (
        "Copy-editing tool for [Journal name](https://example.com). "
        "Authors and editors can upload LaTeX and Quarto sources, convert to "
        "JATS-XML, HTML and PDF, and check and approve the results."
    ),
    "header_branding": "My Journal",
}


def upgrade() -> None:
    with op.batch_alter_table("siteconfig") as batch_op:
        batch_op.add_column(
            sa.Column(
                "site_name", sa.String(), nullable=False,
                server_default=_DEFAULTS["site_name"],
            )
        )
        batch_op.add_column(
            sa.Column(
                "site_description", sa.String(), nullable=False,
                server_default=_DEFAULTS["site_description"],
            )
        )
        batch_op.add_column(
            sa.Column(
                "header_branding", sa.String(), nullable=False,
                server_default=_DEFAULTS["header_branding"],
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("siteconfig") as batch_op:
        batch_op.drop_column("header_branding")
        batch_op.drop_column("site_description")
        batch_op.drop_column("site_name")
