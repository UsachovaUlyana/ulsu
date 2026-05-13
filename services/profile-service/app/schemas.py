from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Gender = Literal["male", "female", "other"]
TargetGender = Literal["male", "female", "any"]


class UserCreate(BaseModel):
    telegram_id: int
    username: str | None = None
    referral_code_used: str | None = Field(default=None, max_length=16)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    referral_code: str
    referred_by: int | None
    created_at: datetime


class ProfileUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    age: int = Field(ge=18, le=100)
    gender: Gender
    city: str | None = Field(default=None, max_length=64)
    bio: str | None = Field(default=None, max_length=2000)
    interests: list[str] | None = Field(default=None, max_length=20)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class ProfileResponse(ProfileUpsert):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    last_active_at: datetime
    updated_at: datetime


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    s3_key: str
    position: int
    url: str | None = None  # populated on read with presigned URL


class PreferencesUpsert(BaseModel):
    target_gender: TargetGender
    age_min: int = Field(ge=18, le=100, default=18)
    age_max: int = Field(ge=18, le=100, default=99)
    max_distance_km: int | None = Field(default=None, ge=1, le=20000)


class PreferencesResponse(PreferencesUpsert):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    updated_at: datetime


class FullProfileResponse(BaseModel):
    user: UserResponse
    profile: ProfileResponse | None
    photos: list[PhotoResponse]
    preferences: PreferencesResponse | None


class ReferralApply(BaseModel):
    inviter_code: str = Field(min_length=4, max_length=16)
    invitee_telegram_id: int


class ReferralResponse(BaseModel):
    inviter_id: int
    invitee_id: int
    bonus_value: float
