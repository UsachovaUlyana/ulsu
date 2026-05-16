"""peer_reviews table + ratings.peer_score column

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add peer_score to existing ratings table
    op.add_column(
        "ratings",
        sa.Column("peer_score", sa.Float, nullable=False, server_default="0"),
    )

    # Create peer_reviews table
    op.create_table(
        "peer_reviews",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "reviewer_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewee_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "score",
            sa.SmallInteger,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("reviewer_id", "reviewee_id", name="uq_peer_review_pair"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_peer_review_score_range"),
        sa.CheckConstraint("reviewer_id <> reviewee_id", name="ck_peer_review_no_self"),
    )
    op.create_index(
        "ix_peer_reviews_reviewee_id", "peer_reviews", ["reviewee_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_peer_reviews_reviewee_id", table_name="peer_reviews")
    op.drop_table("peer_reviews")
    op.drop_column("ratings", "peer_score")
