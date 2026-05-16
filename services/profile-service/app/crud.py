from __future__ import annotations

import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import models, schemas


def _generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    # Avoid confusable chars
    alphabet = alphabet.translate(str.maketrans("", "", "O0I1L"))
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> models.User | None:
    stmt = select(models.User).where(models.User.telegram_id == telegram_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_by_referral_code(
    session: AsyncSession, code: str
) -> models.User | None:
    stmt = select(models.User).where(models.User.referral_code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_user(
    session: AsyncSession, payload: schemas.UserCreate
) -> models.User:
    inviter_id: int | None = None
    if payload.referral_code_used:
        inviter = await get_user_by_referral_code(session, payload.referral_code_used)
        if inviter:
            inviter_id = inviter.id

    # Generate unique referral code with retries
    for _ in range(5):
        code = _generate_referral_code()
        if not await get_user_by_referral_code(session, code):
            break
    else:
        raise RuntimeError("could not allocate unique referral code")

    user = models.User(
        telegram_id=payload.telegram_id,
        username=payload.username,
        referral_code=code,
        referred_by=inviter_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_full_profile(
    session: AsyncSession, telegram_id: int
) -> models.User | None:
    stmt = (
        select(models.User)
        .where(models.User.telegram_id == telegram_id)
        .options(
            selectinload(models.User.profile),
            selectinload(models.User.photos),
            selectinload(models.User.preferences),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_profile(
    session: AsyncSession, user: models.User, payload: schemas.ProfileUpsert
) -> models.Profile:
    existing = await session.get(models.Profile, user.id)
    if existing is None:
        profile = models.Profile(user_id=user.id, **payload.model_dump())
        session.add(profile)
    else:
        for k, v in payload.model_dump().items():
            setattr(existing, k, v)
        profile = existing
    await session.commit()
    await session.refresh(profile)
    return profile


async def upsert_preferences(
    session: AsyncSession, user: models.User, payload: schemas.PreferencesUpsert
) -> models.Preferences:
    existing = await session.get(models.Preferences, user.id)
    if existing is None:
        prefs = models.Preferences(user_id=user.id, **payload.model_dump())
        session.add(prefs)
    else:
        for k, v in payload.model_dump().items():
            setattr(existing, k, v)
        prefs = existing
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def add_photo(
    session: AsyncSession, user: models.User, s3_key: str
) -> models.Photo:
    # position = current count
    existing = (
        await session.execute(
            select(models.Photo).where(models.Photo.user_id == user.id)
        )
    ).scalars().all()
    photo = models.Photo(user_id=user.id, s3_key=s3_key, position=len(existing))
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return photo


async def delete_photo(
    session: AsyncSession, user: models.User, photo_id: int
) -> models.Photo | None:
    photo = await session.get(models.Photo, photo_id)
    if photo is None or photo.user_id != user.id:
        return None
    await session.delete(photo)
    await session.commit()
    return photo


async def create_referral(
    session: AsyncSession, inviter_id: int, invitee_id: int, bonus: float = 0.05
) -> models.Referral | None:
    if inviter_id == invitee_id:
        return None
    existing = (
        await session.execute(
            select(models.Referral).where(models.Referral.invitee_id == invitee_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    ref = models.Referral(
        inviter_id=inviter_id, invitee_id=invitee_id, bonus_value=bonus
    )
    session.add(ref)
    await session.commit()
    await session.refresh(ref)
    return ref


async def delete_user(
    session: AsyncSession, telegram_id: int
) -> models.User | None:
    stmt = (
        select(models.User)
        .where(models.User.telegram_id == telegram_id)
        .options(selectinload(models.User.photos))
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        return None
    await session.delete(user)
    await session.commit()
    return user
