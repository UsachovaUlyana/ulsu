from __future__ import annotations

from app import cache, db
from app.strategies.base import CacheStrategy


class CacheAsideStrategy(CacheStrategy):
    name = "cache_aside"

    async def get(self, item_id: int) -> dict | None:
        cached = await cache.cache_get(item_id)
        if cached is not None:
            return cached
        row = await db.fetch_item(item_id)
        if row is None:
            return None
        await cache.cache_set(item_id, row)
        return row

    async def set(self, item_id: int, payload: str) -> None:
        await db.upsert_item(item_id, payload)
        await cache.cache_delete(item_id)
