"""peer_reviews.score: переход на decimal с шагом 0.1

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-16 09:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_peer_review_score_range", "peer_reviews", type_="check")
    op.alter_column(
        "peer_reviews",
        "score",
        existing_type=sa.SmallInteger(),
        type_=sa.Numeric(2, 1),
        postgresql_using="score::numeric",
    )
    op.create_check_constraint(
        "ck_peer_review_score_range",
        "peer_reviews",
        "score >= 1.0 AND score <= 5.0",
    )
    op.create_check_constraint(
        "ck_peer_review_score_step",
        "peer_reviews",
        "score * 10 = floor(score * 10)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_peer_review_score_step", "peer_reviews", type_="check")
    op.drop_constraint("ck_peer_review_score_range", "peer_reviews", type_="check")
    op.alter_column(
        "peer_reviews",
        "score",
        existing_type=sa.Numeric(2, 1),
        type_=sa.SmallInteger(),
        postgresql_using="round(score)::smallint",
    )
    op.create_check_constraint(
        "ck_peer_review_score_range",
        "peer_reviews",
        "score BETWEEN 1 AND 5",
    )
