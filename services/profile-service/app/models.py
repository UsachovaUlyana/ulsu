from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["Profile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Photo.position"
    )
    preferences: Mapped["Preferences | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("age >= 18 AND age <= 100", name="ck_profile_age"),
        Index("ix_profiles_gender_age", "gender", "age"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(64))
    age: Mapped[int] = mapped_column(SmallInteger)
    gender: Mapped[str] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(64))
    bio: Mapped[str | None] = mapped_column(Text)
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)))
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profile")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    s3_key: Mapped[str] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="photos")


class Preferences(Base):
    __tablename__ = "preferences"
    __table_args__ = (CheckConstraint("age_min <= age_max", name="ck_pref_age_range"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_gender: Mapped[str] = mapped_column(String(16))
    age_min: Mapped[int] = mapped_column(SmallInteger, default=18)
    age_max: Mapped[int] = mapped_column(SmallInteger, default=99)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint("inviter_id <> invitee_id", name="ck_referral_self"),
        UniqueConstraint("invitee_id", name="uq_referral_invitee"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inviter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    invitee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    bonus_value: Mapped[float] = mapped_column(Float, default=0.05)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
