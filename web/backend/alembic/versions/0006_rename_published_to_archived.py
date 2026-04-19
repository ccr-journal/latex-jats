"""Rename ManuscriptStatus.published to archived.

Revision ID: 0006_rename_published_to_archived
Revises: 0005_drop_orcid_auth
Create Date: 2026-04-19
"""

from __future__ import annotations

from alembic import op

revision = "0006_rename_published_to_archived"
down_revision = "0005_drop_orcid_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE manuscript SET status = 'archived' WHERE status = 'published'")


def downgrade() -> None:
    op.execute("UPDATE manuscript SET status = 'published' WHERE status = 'archived'")
