"""Add use_canonical_ccr_cls column to manuscript table.

Revision ID: 0007_add_use_canonical_ccr_cls
Revises: 0006_rename_published_to_archived
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_add_use_canonical_ccr_cls"
down_revision = "0006_rename_published_to_archived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(
            sa.Column(
                "use_canonical_ccr_cls",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("use_canonical_ccr_cls")
