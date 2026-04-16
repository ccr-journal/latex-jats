"""Replace composite PK (manuscript_id, orcid) with auto-increment id on manuscriptauthor.

Makes orcid nullable so authors without an ORCID (imported from OJS) can be
stored for metadata comparison.

Revision ID: 0004_author_id_pk
Revises: 0003_fix_source
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_author_id_pk"
down_revision = "0003_fix_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't support ALTER TABLE to change primary keys, so we
    # recreate the table via batch_alter_table.
    with op.batch_alter_table("manuscriptauthor", recreate="always") as batch:
        batch.add_column(sa.Column("id", sa.Integer(), primary_key=True))
        batch.alter_column("orcid", existing_type=sa.String(), nullable=True)
        # The batch recreation handles PK migration automatically when
        # we declare "id" as the new primary key above.


def downgrade() -> None:
    with op.batch_alter_table("manuscriptauthor", recreate="always") as batch:
        batch.drop_column("id")
        batch.alter_column("orcid", existing_type=sa.String(), nullable=False)
