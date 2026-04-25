"""Add upstream source linkage + main_file column to manuscript (Issue #7).

Revision ID: 0010_add_upstream_source
Revises: 0009_add_manuscript_dates
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_add_upstream_source"
down_revision = "0009_add_manuscript_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.add_column(sa.Column("upstream_url", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("upstream_token_encrypted", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("upstream_ref", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("upstream_subpath", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("main_file", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_synced_sha", sa.String(), nullable=True))

    # Backfill upstream_url for previously-uploaded manuscripts so the unified
    # display works out of the box. For already-uploaded rows the source lives
    # at STORAGE_DIR/manuscripts/<doi>/source — we record the path at the
    # configured storage root. This is display-only; runtime code always reads
    # via storage.source_dir(doi), so if the storage root later moves the
    # stale path is cosmetic and gets overwritten on the next upload.
    import os
    from pathlib import Path as _Path
    project_root = _Path(__file__).resolve().parents[3]
    storage_root = _Path(os.environ.get("STORAGE_DIR", project_root / "storage")).resolve()
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT doi_suffix FROM manuscript "
        "WHERE uploaded_at IS NOT NULL AND upstream_url IS NULL"
    )).fetchall()
    for (doi,) in rows:
        url = (storage_root / "manuscripts" / doi / "source").as_uri()
        bind.execute(
            sa.text("UPDATE manuscript SET upstream_url = :u WHERE doi_suffix = :d"),
            {"u": url, "d": doi},
        )


def downgrade() -> None:
    with op.batch_alter_table("manuscript") as batch_op:
        batch_op.drop_column("last_synced_sha")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("main_file")
        batch_op.drop_column("upstream_subpath")
        batch_op.drop_column("upstream_ref")
        batch_op.drop_column("upstream_token_encrypted")
        batch_op.drop_column("upstream_url")
