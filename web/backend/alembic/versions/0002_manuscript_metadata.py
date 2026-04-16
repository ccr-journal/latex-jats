"""Add OJS-imported metadata columns to manuscript.

Revision ID: 0002_manuscript_metadata
Revises: 0001_baseline
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_manuscript_metadata"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch:
        batch.add_column(sa.Column("title", sa.String(), nullable=True))
        batch.add_column(sa.Column("abstract", sa.Text(), nullable=True))
        batch.add_column(sa.Column("keywords", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("doi", sa.String(), nullable=True))
        batch.add_column(sa.Column("volume", sa.String(), nullable=True))
        batch.add_column(sa.Column("issue_number", sa.String(), nullable=True))
        batch.add_column(sa.Column("year", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch:
        batch.drop_column("year")
        batch.drop_column("issue_number")
        batch.drop_column("volume")
        batch.drop_column("doi")
        batch.drop_column("keywords")
        batch.drop_column("abstract")
        batch.drop_column("title")
