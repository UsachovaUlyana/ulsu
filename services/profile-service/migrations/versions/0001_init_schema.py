"""initial schema — all tables for the whole system

Created here once because profile-service owns the single Alembic history;
other services declare ORM models against the same tables without migrations.

Revision ID: 0001
Revises:
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("referral_code", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column("referred_by", sa.BigInteger, sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "profiles",
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("age", sa.SmallInteger, nullable=False),
        sa.Column("gender", sa.String(16), nullable=False),  # male/female/other
        sa.Column("city", sa.String(64), nullable=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("interests", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lon", sa.Float, nullable=True),
        sa.Column(
            "last_active_at",
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
        sa.CheckConstraint("age >= 18 AND age <= 100", name="ck_profile_age"),
    )
    op.create_index("ix_profiles_gender_age", "profiles", ["gender", "age"])

    op.create_table(
        "photos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("s3_key", sa.String(256), nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "preferences",
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("target_gender", sa.String(16), nullable=False),  # male/female/any
        sa.Column("age_min", sa.SmallInteger, nullable=False, server_default="18"),
        sa.Column("age_max", sa.SmallInteger, nullable=False, server_default="99"),
        sa.Column("max_distance_km", sa.Integer, nullable=True),  # NULL = no limit
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("age_min <= age_max", name="ck_pref_age_range"),
    )

    # Swipes — owned by matching-service but schema lives here
    op.create_table(
        "swipes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "swiper_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(8), nullable=False),  # like / skip
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("swiper_id", "target_id", name="uq_swipe_pair"),
        sa.CheckConstraint("action IN ('like','skip')", name="ck_swipe_action"),
        sa.CheckConstraint("swiper_id <> target_id", name="ck_swipe_self"),
    )
    op.create_index("ix_swipes_target_action", "swipes", ["target_id", "action"])

    # Matches — pair of users (user1_id < user2_id by convention to dedupe)
    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user1_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user2_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_dialog_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user1_id", "user2_id", name="uq_match_pair"),
        sa.CheckConstraint("user1_id < user2_id", name="ck_match_order"),
    )

    # Ratings — owned by ranking-service
    op.create_table(
        "ratings",
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("primary_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("behavioral_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("referral_bonus", sa.Float, nullable=False, server_default="0"),
        sa.Column("combined_score", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ratings_combined", "ratings", ["combined_score"])

    # Activity log — for L2 temporal factor (which hours the user is active)
    op.create_table(
        "activity_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("hour_of_day", sa.SmallInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Referrals
    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "inviter_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invitee_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # one invitee can be referred only once
        ),
        sa.Column("bonus_value", sa.Float, nullable=False, server_default="0.05"),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("inviter_id <> invitee_id", name="ck_referral_self"),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("activity_log")
    op.drop_index("ix_ratings_combined", table_name="ratings")
    op.drop_table("ratings")
    op.drop_table("matches")
    op.drop_index("ix_swipes_target_action", table_name="swipes")
    op.drop_table("swipes")
    op.drop_table("preferences")
    op.drop_table("photos")
    op.drop_index("ix_profiles_gender_age", table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("users")
