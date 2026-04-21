"""Add primary_contact column to manuscriptauthor table.

Revision ID: 0008_add_author_primary_contact
Revises: 0007_add_use_canonical_ccr_cls
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_add_author_primary_contact"
down_revision = "0007_add_use_canonical_ccr_cls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.add_column(
            sa.Column(
                "primary_contact",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.drop_column("primary_contact")
