"""Rename manuscript.use_canonical_ccr_cls to use_canonical_class_file (#32).

The toggle's underlying behaviour is now journal-agnostic — it installs
whatever the deployer's configured canonical class file is, not specifically
ccr.cls. Rename the column to match.

Revision ID: 0016_rename_use_canonical_class_file
Revises: 0015_add_canonical_urls
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op

revision = "0016_rename_use_canonical_class_file"
down_revision = "0015_add_canonical_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.alter_column(
            "use_canonical_ccr_cls",
            new_column_name="use_canonical_class_file",
        )


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.alter_column(
            "use_canonical_class_file",
            new_column_name="use_canonical_ccr_cls",
        )
