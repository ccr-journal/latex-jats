"""Baseline schema with manuscriptauthor

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-15

Creates all tables (manuscript, accesstoken, loginstate, manuscriptauthor).
For databases created before Alembic was introduced (dev sqlite files),
`alembic stamp 0001_baseline` after confirming the schema already matches.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "manuscript" not in existing:
        op.create_table(
            "manuscript",
            sa.Column("doi_suffix", sa.String(), primary_key=True),
            sa.Column("ojs_submission_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(), nullable=True),
            sa.Column("uploaded_by", sa.String(), nullable=True),
            sa.Column("job_log", sa.Text(), nullable=False),
            sa.Column("job_started_at", sa.DateTime(), nullable=True),
            sa.Column("job_completed_at", sa.DateTime(), nullable=True),
            sa.Column("pipeline_steps", sa.JSON(), nullable=True),
        )

    if "accesstoken" not in existing:
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

    if "loginstate" not in existing:
        op.create_table(
            "loginstate",
            sa.Column("state", sa.String(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "manuscriptauthor" not in existing:
        op.create_table(
            "manuscriptauthor",
            sa.Column(
                "manuscript_id",
                sa.String(),
                sa.ForeignKey("manuscript.doi_suffix"),
                primary_key=True,
            ),
            sa.Column("orcid", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index(
            "ix_manuscriptauthor_orcid", "manuscriptauthor", ["orcid"]
        )


def downgrade() -> None:
    op.drop_index("ix_manuscriptauthor_orcid", table_name="manuscriptauthor")
    op.drop_table("manuscriptauthor")
    op.drop_table("loginstate")
    op.drop_index("ix_accesstoken_orcid", table_name="accesstoken")
    op.drop_index("ix_accesstoken_token", table_name="accesstoken")
    op.drop_table("accesstoken")
    op.drop_table("manuscript")
