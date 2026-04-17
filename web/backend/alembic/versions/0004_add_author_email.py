"""Add email column to manuscriptauthor table.

Revision ID: 0004_add_author_email
Revises: 0003_add_manuscript_token
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_add_author_email"
down_revision = "0003_add_manuscript_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.drop_column("email")
