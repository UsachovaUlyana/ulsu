"""Redis storage for FSM state persistence."""

from redis.asyncio import Redis

from app.config import settings


async def get_redis() -> Redis:
    """Get Redis connection for FSM storage."""
    return Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )
