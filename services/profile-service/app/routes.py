from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.metrics import registrations_total, referrals_applied_total

from . import crud, schemas
from .database import get_session
from .events_publisher import emit_profile_updated, emit_referral_applied
from .minio_service import get_minio

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")


def _user_or_404(user) -> None:
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")


def _photo_response(photo, minio) -> schemas.PhotoResponse:
    return schemas.PhotoResponse(
        id=photo.id,
        s3_key=photo.s3_key,
        position=photo.position,
        url=minio.presigned_url(photo.s3_key),
    )


@router.post(
    "/users/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: schemas.UserCreate, session: AsyncSession = Depends(get_session)
):
    existing = await crud.get_user_by_telegram_id(session, payload.telegram_id)
    if existing:
        return existing
    user = await crud.create_user(session, payload)
    registrations_total.inc()
    logger.info(
        "user_created",
        telegram_id=user.telegram_id,
        user_id=user.id,
        referral_code=user.referral_code,
    )
    return user


@router.get("/users/{telegram_id}", response_model=schemas.FullProfileResponse)
async def get_user(telegram_id: int, session: AsyncSession = Depends(get_session)):
    user = await crud.get_full_profile(session, telegram_id)
    _user_or_404(user)
    minio = get_minio()
    return schemas.FullProfileResponse(
        user=schemas.UserResponse.model_validate(user),
        profile=schemas.ProfileResponse.model_validate(user.profile)
        if user.profile
        else None,
        photos=[_photo_response(p, minio) for p in user.photos],
        preferences=schemas.PreferencesResponse.model_validate(user.preferences)
        if user.preferences
        else None,
    )


@router.put("/users/{telegram_id}/profile", response_model=schemas.ProfileResponse)
async def upsert_profile(
    telegram_id: int,
    payload: schemas.ProfileUpsert,
    session: AsyncSession = Depends(get_session),
):
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    _user_or_404(user)
    profile = await crud.upsert_profile(session, user, payload)
    await emit_profile_updated(user.id, telegram_id)
    return profile


@router.put(
    "/users/{telegram_id}/preferences", response_model=schemas.PreferencesResponse
)
async def upsert_preferences(
    telegram_id: int,
    payload: schemas.PreferencesUpsert,
    session: AsyncSession = Depends(get_session),
):
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    _user_or_404(user)
    prefs = await crud.upsert_preferences(session, user, payload)
    await emit_profile_updated(user.id, telegram_id)
    return prefs


@router.post(
    "/users/{telegram_id}/photos",
    response_model=schemas.PhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photo(
    telegram_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    _user_or_404(user)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="photo too large (max 5MB)")
    minio = get_minio()
    s3_key = minio.upload(
        telegram_id, data, content_type=file.content_type or "image/jpeg"
    )
    photo = await crud.add_photo(session, user, s3_key)
    await emit_profile_updated(user.id, telegram_id)
    return _photo_response(photo, minio)


@router.delete(
    "/users/{telegram_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_photo(
    telegram_id: int, photo_id: int, session: AsyncSession = Depends(get_session)
):
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    _user_or_404(user)
    photo = await crud.delete_photo(session, user, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    get_minio().delete(photo.s3_key)
    await emit_profile_updated(user.id, telegram_id)
    return None


@router.post(
    "/referrals/apply",
    response_model=schemas.ReferralResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_referral(
    payload: schemas.ReferralApply, session: AsyncSession = Depends(get_session)
):
    invitee = await crud.get_user_by_telegram_id(
        session, payload.invitee_telegram_id
    )
    _user_or_404(invitee)
    inviter = await crud.get_user_by_referral_code(session, payload.inviter_code)
    if inviter is None:
        raise HTTPException(status_code=404, detail="invalid referral code")
    if inviter.id == invitee.id:
        raise HTTPException(status_code=400, detail="self-referral not allowed")

    ref = await crud.create_referral(session, inviter.id, invitee.id)
    if ref is None:
        raise HTTPException(status_code=409, detail="referral already applied")

    await emit_referral_applied(inviter.id, invitee.id, ref.bonus_value)
    referrals_applied_total.inc()
    return schemas.ReferralResponse(
        inviter_id=inviter.id, invitee_id=invitee.id, bonus_value=ref.bonus_value
    )


@router.get("/health")
async def health():
    return {"status": "ok"}
