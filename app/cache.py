from __future__ import annotations

import json
import os

from redis.asyncio import Redis

from app.metrics import metrics


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def cache_get(item_id: int) -> dict | None:
    r = get_redis()
    raw = await r.get(_key(item_id))
    if raw is None:
        metrics.incr("cache_misses")
        return None
    metrics.incr("cache_hits")
    return json.loads(raw)


async def cache_set(item_id: int, value: dict, ttl: int | None = None) -> None:
    r = get_redis()
    await r.set(_key(item_id), json.dumps(value), ex=ttl if ttl is not None else CACHE_TTL)


async def cache_delete(item_id: int) -> None:
    r = get_redis()
    await r.delete(_key(item_id))


async def cache_flushdb() -> None:
    r = get_redis()
    await r.flushdb()


async def redis_info_stats() -> dict:
    r = get_redis()
    info = await r.info("stats")
    return {
        "keyspace_hits": int(info.get("keyspace_hits", 0)),
        "keyspace_misses": int(info.get("keyspace_misses", 0)),
    }


def _key(item_id: int) -> str:
    return f"item:{item_id}"
