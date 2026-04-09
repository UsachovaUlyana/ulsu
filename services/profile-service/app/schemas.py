"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# User schemas
# ============================================================


class UserCreate(BaseModel):
    """Schema for creating a user (from Bot Service)."""

    telegram_id: int
    username: Optional[str] = None


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int
    telegram_id: int
    username: Optional[str] = None
    referral_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Profile schemas
# ============================================================


class ProfileCreate(BaseModel):
    """Schema for creating a profile."""

    name: str = Field(..., min_length=2, max_length=100)
    age: int = Field(..., ge=18, le=100)
    gender: str = Field(..., pattern="^(male|female|other)$")
    city: str = Field(..., min_length=2, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    interests: Optional[List[str]] = None


class ProfileUpdate(BaseModel):
    """Schema for updating a profile."""

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    age: Optional[int] = Field(None, ge=18, le=100)
    gender: Optional[str] = Field(None, pattern="^(male|female|other)$")
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    interests: Optional[List[str]] = None
    is_complete: Optional[bool] = None


class ProfileResponse(BaseModel):
    """Schema for profile response."""

    id: int
    user_id: int
    name: str
    age: int
    gender: str
    city: str
    bio: Optional[str] = None
    interests: Optional[List[str]] = None
    is_complete: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Photo schemas
# ============================================================


class PhotoResponse(BaseModel):
    """Schema for photo response."""

    id: int
    profile_id: int
    s3_key: str
    s3_bucket: str
    is_primary: bool
    upload_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Preferences schemas
# ============================================================


class PreferencesUpdate(BaseModel):
    """Schema for updating search preferences."""

    target_gender: str = Field(..., pattern="^(male|female|any)$")
    age_min: int = Field(18, ge=18, le=100)
    age_max: int = Field(100, ge=18, le=100)
    city: Optional[str] = None
    max_distance: Optional[int] = None


class PreferencesResponse(BaseModel):
    """Schema for preferences response."""

    id: int
    user_id: int
    target_gender: str
    age_min: int
    age_max: int
    city: Optional[str] = None
    max_distance: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Full profile response (user + profile + photos + preferences)
# ============================================================


class FullProfileResponse(BaseModel):
    """Complete profile data with user info, photos, and preferences."""

    user: UserResponse
    profile: Optional[ProfileResponse] = None
    photos: List[PhotoResponse] = []
    preferences: Optional[PreferencesResponse] = None
