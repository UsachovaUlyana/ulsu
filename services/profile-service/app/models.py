"""SQLAlchemy database models."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    ARRAY,
    CheckConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """User model — base entity created on /start."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=lambda: f"ref_{id}")
    referred_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    profile: Mapped[Optional["Profile"]] = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences: Mapped[Optional["Preferences"]] = relationship("Preferences", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    """Profile model — user's dating profile/anketa."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interests: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("age >= 18 AND age <= 100", name="check_age_range"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="profile", cascade="all, delete-orphan", order_by="Photo.upload_order")


class Photo(Base):
    """Photo model — user's uploaded photos stored in MinIO."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("profiles.id"), nullable=False, index=True)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(100), nullable=False, default="photos")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    upload_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="photos")


class Preferences(Base):
    """Preferences model — user's search criteria."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    target_gender: Mapped[str] = mapped_column(String(20), nullable=False)
    age_min: Mapped[int] = mapped_column(SmallInteger, default=18)
    age_max: Mapped[int] = mapped_column(SmallInteger, default=100)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_distance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("age_min >= 18", name="check_age_min"),
        CheckConstraint("age_max <= 100", name="check_age_max"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")
