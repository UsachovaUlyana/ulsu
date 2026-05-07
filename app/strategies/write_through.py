from __future__ import annotations

from datetime import datetime, timezone

from app import cache, db
from app.strategies.base import CacheStrategy


class WriteThroughStrategy(CacheStrategy):
    name = "write_through"

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
        await cache.cache_set(
            item_id,
            {"id": item_id, "payload": payload, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
