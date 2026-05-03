"""Drop ojs_base_url and ojs_journal_path from siteconfig (Issue #32 follow-up).

Those values move back into env vars next to OJS_ADMIN_TOKEN — they're
useless without the admin token, so splitting "OJS integration" between the
DB form and the env file gave editors two places to look. The DOI prefix
stays in SiteConfig because it's also used in JATS journal-meta output.

Revision ID: 0013_drop_siteconfig_ojs_cols
Revises: 0012_add_site_config
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_drop_siteconfig_ojs_cols"
down_revision = "0012_add_site_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: amended 0012 no longer adds these columns, so a fresh DB
    # never has them — only DBs that ran the original 0012 do. Check before
    # dropping so both paths converge cleanly at this revision.
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("siteconfig")}
    to_drop = [c for c in ("ojs_base_url", "ojs_journal_path") if c in cols]
    if not to_drop:
        return
    with op.batch_alter_table("siteconfig") as batch_op:
        for name in to_drop:
            batch_op.drop_column(name)


def downgrade() -> None:
    with op.batch_alter_table("siteconfig") as batch_op:
        batch_op.add_column(
            sa.Column("ojs_base_url", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("ojs_journal_path", sa.String(), nullable=False, server_default="")
        )
