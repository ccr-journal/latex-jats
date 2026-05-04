"""Add notify_email column to manuscript table (Issue #37).

Holds the recipient address for the optional "email me when conversion is
done" opt-in. Set by POST /process when the user opts in; cleared by the
worker after a successful send so the column is idempotent across re-runs.

Revision ID: 0017_add_manuscript_notify_email
Revises: 0016_rename_use_canonical_class_file
Create Date: 2026-05-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_add_manuscript_notify_email"
down_revision = "0016_rename_use_canonical_class_file"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(sa.Column("notify_email", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("notify_email")
