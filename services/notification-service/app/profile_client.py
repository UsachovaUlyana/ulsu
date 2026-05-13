"""Read-only HTTP client for profile-service used to fetch the matched
partner's display info (name, age) and interests for icebreakers."""

from __future__ import annotations

import aiohttp

from shared.logging import get_logger

from .config import settings

logger = get_logger(__name__)


async def get_user(telegram_id: int) -> dict | None:
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            async with session.get(
                f"{settings.profile_service_url}/api/v1/users/{telegram_id}"
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception:
        logger.exception("profile_lookup_failed", telegram_id=telegram_id)
        return None
