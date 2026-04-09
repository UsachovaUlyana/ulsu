"""CRUD operations for users, profiles, photos, and preferences."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.models import User, Profile, Photo, Preferences
from app.schemas import ProfileUpdate, PreferencesUpdate

logger = structlog.get_logger(__name__)


# ============================================================
# User CRUD
# ============================================================


async def create_user(db: AsyncSession, telegram_id: int, username: Optional[str] = None) -> User:
    """Create a new user with unique referral code."""
    referral_code = f"ref_{uuid.uuid4().hex[:8]}"

    user = User(
        telegram_id=telegram_id,
        username=username,
        referral_code=referral_code,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("user_created", telegram_id=telegram_id, user_id=user.id)
    return user


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
    """Get user by Telegram ID."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get user by internal ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ============================================================
# Profile CRUD
# ============================================================


async def create_or_update_profile(
    db: AsyncSession, user_id: int, profile_data: ProfileUpdate
) -> Profile:
    """Create or update user profile."""
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Check if profile exists
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()

    if profile:
        # Update existing
        update_data = profile_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.utcnow()
        logger.info("profile_updated", user_id=user_id)
    else:
        # Create new
        profile = Profile(
            user_id=user_id,
            **profile_data.model_dump(),
        )
        db.add(profile)
        logger.info("profile_created", user_id=user_id)

    await db.flush()
    await db.refresh(profile)
    return profile


async def get_profile_by_user_id(db: AsyncSession, telegram_id: int) -> Optional[Profile]:
    """Get profile by user's Telegram ID."""
    result = await db.execute(
        select(Profile)
        .join(User)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(Profile.photos))
    )
    return result.scalar_one_or_none()


# ============================================================
# Photo CRUD
# ============================================================


async def create_photo(
    db: AsyncSession,
    profile_id: int,
    s3_key: str,
    s3_bucket: str = "photos",
    is_primary: bool = False,
) -> Photo:
    """Create a new photo record."""
    # Get upload order
    result = await db.execute(
        select(Photo).where(Photo.profile_id == profile_id).order_by(Photo.upload_order.desc()).limit(1)
    )
    last_photo = result.scalar_one_or_none()
    upload_order = (last_photo.upload_order + 1) if last_photo else 1

    # If this is primary, unset other primary photos
    if is_primary:
        await db.execute(
            update(Photo).where(Photo.profile_id == profile_id).values(is_primary=False)
        )

    photo = Photo(
        profile_id=profile_id,
        s3_key=s3_key,
        s3_bucket=s3_bucket,
        is_primary=is_primary,
        upload_order=upload_order,
    )
    db.add(photo)
    await db.flush()
    await db.refresh(photo)

    logger.info("photo_created", profile_id=profile_id, photo_id=photo.id)
    return photo


async def get_photos_by_profile_id(db: AsyncSession, profile_id: int) -> List[Photo]:
    """Get all photos for a profile."""
    result = await db.execute(
        select(Photo).where(Photo.profile_id == profile_id).order_by(Photo.upload_order)
    )
    return list(result.scalars().all())


# ============================================================
# Preferences CRUD
# ============================================================


async def create_or_update_preferences(
    db: AsyncSession, user_id: int, preferences_data: PreferencesUpdate
) -> Preferences:
    """Create or update user search preferences."""
    result = await db.execute(select(Preferences).where(Preferences.user_id == user_id))
    preferences = result.scalar_one_or_none()

    if preferences:
        # Update existing
        update_data = preferences_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(preferences, field, value)
        preferences.updated_at = datetime.utcnow()
        logger.info("preferences_updated", user_id=user_id)
    else:
        # Create new
        preferences = Preferences(
            user_id=user_id,
            **preferences_data.model_dump(),
        )
        db.add(preferences)
        logger.info("preferences_created", user_id=user_id)

    await db.flush()
    await db.refresh(preferences)
    return preferences


async def get_preferences_by_user_id(db: AsyncSession, telegram_id: int) -> Optional[Preferences]:
    """Get preferences by user's Telegram ID."""
    result = await db.execute(
        select(Preferences).join(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()
