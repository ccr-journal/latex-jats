"""Add diagnosis_chat table (Issue #36).

One Claude diagnosis chat per manuscript. Editors and the manuscript's
author can append turns; the editor can also reset (delete) the chat.

Revision ID: 0018_add_diagnosis_chat
Revises: 0017_add_manuscript_notify_email
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_add_diagnosis_chat"
down_revision = "0017_add_manuscript_notify_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosischat",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "manuscript_id",
            sa.String(),
            sa.ForeignKey("manuscript.doi_suffix"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("diagnosischat")
