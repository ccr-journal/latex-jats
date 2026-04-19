"""Drop ORCID auth plumbing and ManuscriptAuthor.orcid.

- Replace ``accesstoken.orcid`` with ``accesstoken.username`` (recreates the
  table; existing sessions are invalidated, which is correct since they were
  ORCID-based).
- Drop the ``manuscriptauthor.orcid`` column (unused).
- Drop the ``loginstate`` table (ORCID OAuth state store, no longer needed).

Revision ID: 0005_drop_orcid_auth
Revises: 0004_add_author_email
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_drop_orcid_auth"
down_revision = "0004_add_author_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Clean up leftover `_alembic_tmp_<table>` staging tables from any
    # previously failed batch_alter_table run so we don't collide with them.
    for stale in ("_alembic_tmp_manuscriptauthor", "_alembic_tmp_accesstoken"):
        if stale in tables:
            op.drop_table(stale)

    if "loginstate" in tables:
        op.drop_table("loginstate")

    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.drop_index("ix_manuscriptauthor_orcid")
        batch_op.drop_column("orcid")

    # Recreate accesstoken with username instead of orcid. SQLite batch-alter
    # can't cleanly combine a column rename with an index rename in one pass,
    # and existing ORCID sessions should be invalidated anyway.
    op.drop_index("ix_accesstoken_orcid", table_name="accesstoken")
    op.drop_index("ix_accesstoken_token", table_name="accesstoken")
    op.drop_table("accesstoken")
    op.create_table(
        "accesstoken",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_accesstoken_token", "accesstoken", ["token"], unique=True)
    op.create_index("ix_accesstoken_username", "accesstoken", ["username"])


def downgrade() -> None:
    op.drop_index("ix_accesstoken_username", table_name="accesstoken")
    op.drop_index("ix_accesstoken_token", table_name="accesstoken")
    op.drop_table("accesstoken")
    op.create_table(
        "accesstoken",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("orcid", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_accesstoken_token", "accesstoken", ["token"], unique=True)
    op.create_index("ix_accesstoken_orcid", "accesstoken", ["orcid"])

    with op.batch_alter_table("manuscriptauthor") as batch_op:
        batch_op.add_column(sa.Column("orcid", sa.String(), nullable=True))
        batch_op.create_index("ix_manuscriptauthor_orcid", ["orcid"])

    op.create_table(
        "loginstate",
        sa.Column("state", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
