"""Add approved_at/approved_by audit columns to manuscript (Issue #9).

Revision ID: 0011_add_approval_audit
Revises: 0010_add_upstream_source
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_add_approval_audit"
down_revision = "0010_add_upstream_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("approved_by")
        batch_op.drop_column("approved_at")
