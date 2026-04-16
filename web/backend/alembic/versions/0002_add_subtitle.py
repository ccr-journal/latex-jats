"""Add subtitle column to manuscript table.

Revision ID: 0002_add_subtitle
Revises: 0001_baseline
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_add_subtitle"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(sa.Column("subtitle", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("subtitle")
