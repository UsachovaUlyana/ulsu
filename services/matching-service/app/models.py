from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Swipe(Base):
    __tablename__ = "swipes"
    __table_args__ = (
        UniqueConstraint("swiper_id", "target_id", name="uq_swipe_pair"),
        CheckConstraint("action IN ('like','skip')", name="ck_swipe_action"),
        CheckConstraint("swiper_id <> target_id", name="ck_swipe_self"),
        Index("ix_swipes_target_action", "target_id", "action"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    swiper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("user1_id", "user2_id", name="uq_match_pair"),
        CheckConstraint("user1_id < user2_id", name="ck_match_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user1_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    user2_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_dialog_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
