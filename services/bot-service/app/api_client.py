"""HTTP client for Profile Service API integration."""

from typing import Any

import aiohttp
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class ProfileServiceClient:
    """Async HTTP client for communicating with Profile Service."""

    def __init__(self) -> None:
        self._base_url = settings.profile_service_url
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def create_user(self, telegram_id: int, username: str | None = None) -> dict[str, Any]:
        """Register a new user in Profile Service."""
        session = await self._get_session()
        payload = {
            "telegram_id": telegram_id,
            "username": username,
        }
        try:
            async with session.post(
                f"{self._base_url}/api/v1/users/", json=payload
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info("user_created", telegram_id=telegram_id)
                return result
        except aiohttp.ClientError as e:
            logger.error("user_creation_failed", telegram_id=telegram_id, error=str(e))
            raise

    async def update_profile(self, telegram_id: int, profile_data: dict[str, Any]) -> dict[str, Any]:
        """Update user profile in Profile Service."""
        session = await self._get_session()
        try:
            async with session.put(
                f"{self._base_url}/api/v1/users/{telegram_id}", json=profile_data
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info("profile_updated", telegram_id=telegram_id)
                return result
        except aiohttp.ClientError as e:
            logger.error("profile_update_failed", telegram_id=telegram_id, error=str(e))
            raise

    async def get_profile(self, telegram_id: int) -> dict[str, Any]:
        """Get user profile from Profile Service."""
        session = await self._get_session()
        try:
            async with session.get(
                f"{self._base_url}/api/v1/users/{telegram_id}"
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return result
        except aiohttp.ClientError as e:
            logger.error("profile_fetch_failed", telegram_id=telegram_id, error=str(e))
            raise

    async def upload_photo(self, telegram_id: int, photo_bytes: bytes, filename: str) -> dict[str, Any]:
        """Upload a photo for user via Profile Service."""
        session = await self._get_session()
        data = aiohttp.FormData()
        data.add_field(
            "photo",
            photo_bytes,
            filename=filename,
            content_type="image/jpeg",
        )
        try:
            async with session.post(
                f"{self._base_url}/api/v1/users/{telegram_id}/photos", data=data
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info(
                    "photo_uploaded", telegram_id=telegram_id, filename=filename
                )
                return result
        except aiohttp.ClientError as e:
            logger.error("photo_upload_failed", telegram_id=telegram_id, error=str(e))
            raise

    async def update_preferences(
        self, telegram_id: int, preferences: dict[str, Any]
    ) -> dict[str, Any]:
        """Update user search preferences."""
        session = await self._get_session()
        try:
            async with session.put(
                f"{self._base_url}/api/v1/users/{telegram_id}/preferences",
                json=preferences,
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info("preferences_updated", telegram_id=telegram_id)
                return result
        except aiohttp.ClientError as e:
            logger.error(
                "preferences_update_failed", telegram_id=telegram_id, error=str(e)
            )
            raise


# Singleton instance
profile_client = ProfileServiceClient()
