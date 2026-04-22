"""Add date_received / date_accepted / date_published columns to manuscript.

Revision ID: 0009_add_manuscript_dates
Revises: 0008_add_author_primary_contact
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_add_manuscript_dates"
down_revision = "0008_add_author_primary_contact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(sa.Column("date_received", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("date_accepted", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("date_published", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("date_published")
        batch_op.drop_column("date_accepted")
        batch_op.drop_column("date_received")
