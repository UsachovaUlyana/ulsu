"""API routes for user management."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.schemas import (
    UserCreate,
    UserResponse,
    ProfileUpdate,
    ProfileResponse,
    PhotoResponse,
    PreferencesUpdate,
    PreferencesResponse,
    FullProfileResponse,
)
from app import crud
from app.minio_service import upload_photo

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user by Telegram ID."""
    # Check if user already exists
    existing_user = await crud.get_user_by_telegram_id(db, user_data.telegram_id)
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    user = await crud.create_user(db, user_data.telegram_id, user_data.username)
    return user


@router.get("/{telegram_id}", response_model=FullProfileResponse)
async def get_user_profile(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get complete user profile with photos and preferences."""
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await crud.get_profile_by_user_id(db, telegram_id)
    preferences = await crud.get_preferences_by_user_id(db, telegram_id)

    # Build response
    photos = []
    if profile:
        photos_db = await crud.get_photos_by_profile_id(db, profile.id)
        for photo in photos_db:
            photos.append(
                PhotoResponse(
                    id=photo.id,
                    profile_id=photo.profile_id,
                    s3_key=photo.s3_key,
                    s3_bucket=photo.s3_bucket,
                    is_primary=photo.is_primary,
                    upload_order=photo.upload_order,
                    created_at=photo.created_at,
                )
            )

    return FullProfileResponse(
        user=UserResponse.model_validate(user),
        profile=ProfileResponse.model_validate(profile) if profile else None,
        photos=photos,
        preferences=PreferencesResponse.model_validate(preferences) if preferences else None,
    )


@router.put("/{telegram_id}", response_model=ProfileResponse)
async def update_profile(
    telegram_id: int,
    profile_data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update user profile."""
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        profile = await crud.create_or_update_profile(db, user.id, profile_data)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{telegram_id}/photos", response_model=PhotoResponse, status_code=201)
async def upload_user_photo(
    telegram_id: int,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a photo for user."""
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await crud.get_profile_by_user_id(db, telegram_id)
    
    # Auto-create profile if it doesn't exist yet (during registration)
    if not profile:
        from app.schemas import ProfileCreate
        profile = await crud.create_or_update_profile(
            db, user.id,
            ProfileCreate(name="Temp", age=18, gender="other", city="Unknown")
        )

    # Check photo limit
    existing_photos = await crud.get_photos_by_profile_id(db, profile.id)
    if len(existing_photos) >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 photos allowed")

    # Upload to MinIO
    photo_bytes = await photo.read()
    s3_key = await upload_photo(photo_bytes, photo.filename or "photo.jpg")

    # Save photo record
    photo_record = await crud.create_photo(
        db,
        profile_id=profile.id,
        s3_key=s3_key,
        is_primary=(len(existing_photos) == 0),  # First photo is primary
    )

    return photo_record


@router.delete("/{telegram_id}/photos/{photo_id}")
async def delete_user_photo(
    telegram_id: int,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a user's photo."""
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await crud.get_profile_by_user_id(db, telegram_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Find photo
    photos = await crud.get_photos_by_profile_id(db, profile.id)
    photo_to_delete = next((p for p in photos if p.id == photo_id), None)
    if not photo_to_delete:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Delete from MinIO and DB
    from app.minio_service import delete_photo
    await delete_photo(photo_to_delete.s3_key)
    # TODO: delete from DB (need delete implementation in CRUD)

    return {"message": "Photo deleted"}


@router.get("/{telegram_id}/preferences", response_model=PreferencesResponse)
async def get_user_preferences(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get user search preferences."""
    preferences = await crud.get_preferences_by_user_id(db, telegram_id)
    if not preferences:
        raise HTTPException(status_code=404, detail="Preferences not found")

    return preferences


@router.put("/{telegram_id}/preferences", response_model=PreferencesResponse)
async def update_user_preferences(
    telegram_id: int,
    preferences_data: PreferencesUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update user search preferences."""
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    preferences = await crud.create_or_update_preferences(db, user.id, preferences_data)
    return preferences
