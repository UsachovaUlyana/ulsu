"""Pulls photo presigned URLs from profile-service. Used to enrich /feed
responses without duplicating MinIO logic in ranking-service."""

from __future__ import annotations

import aiohttp

from shared.logging import get_logger

logger = get_logger(__name__)

PROFILE_SERVICE_URL = "http://profile-service:8001"


async def get_photos(telegram_id: int) -> list[dict]:
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            async with session.get(
                f"{PROFILE_SERVICE_URL}/api/v1/users/{telegram_id}"
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("photos") or []
    except Exception:
        logger.exception("photos_fetch_failed", telegram_id=telegram_id)
        return []
