"""add search_city to preferences

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16 03:00:00.000000+00:00

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preferences",
        sa.Column("search_city", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("preferences", "search_city")
