"""Add manuscript_token table for per-manuscript author access links.

Revision ID: 0003_add_manuscript_token
Revises: 0002_add_subtitle
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_add_manuscript_token"
down_revision = "0002_add_subtitle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manuscripttoken",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "manuscript_id",
            sa.String(),
            sa.ForeignKey("manuscript.doi_suffix"),
            nullable=False,
            unique=True,
        ),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_manuscripttoken_token", "manuscripttoken", ["token"])
    op.create_index(
        "ix_manuscripttoken_manuscript_id", "manuscripttoken", ["manuscript_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_manuscripttoken_manuscript_id", "manuscripttoken")
    op.drop_index("ix_manuscripttoken_token", "manuscripttoken")
    op.drop_table("manuscripttoken")
