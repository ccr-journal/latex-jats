"""Add fix_source column to manuscript.

Revision ID: 0003_fix_source
Revises: 0002_manuscript_metadata
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_fix_source"
down_revision = "0002_manuscript_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch:
        batch.add_column(
            sa.Column("fix_source", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch:
        batch.drop_column("fix_source")
