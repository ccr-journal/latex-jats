"""Add canonical class-file & Quarto-extension URL columns to siteconfig (#32).

Both fields are optional and start blank. The editor pastes them into the
SiteConfig form post-upgrade; the lifespan handler then fetches the canonical
bundle into ``STORAGE_DIR/canonical/``. No backfill — even existing CCR
deployments are treated like any other journal.

Revision ID: 0015_add_canonical_urls
Revises: 0014_add_siteconfig_branding
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_add_canonical_urls"
down_revision = "0014_add_siteconfig_branding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("siteconfig") as batch_op:
        batch_op.add_column(
            sa.Column(
                "class_file_url", sa.String(), nullable=False, server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "quarto_extension_repo", sa.String(), nullable=False, server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("siteconfig") as batch_op:
        batch_op.drop_column("quarto_extension_repo")
        batch_op.drop_column("class_file_url")
