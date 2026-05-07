from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from app import cache, db
from app.metrics import metrics
from app.strategies.base import CacheStrategy


WB_FLUSH_INTERVAL = float(os.getenv("WB_FLUSH_INTERVAL", "1.0"))
WB_FLUSH_BATCH = int(os.getenv("WB_FLUSH_BATCH", "500"))


class WriteBackStrategy(CacheStrategy):
    name = "write_back"

    def __init__(self) -> None:
        self._dirty: dict[int, str] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._wakeup = asyncio.Event()

    async def startup(self) -> None:
        self._stop.clear()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush_loop(), name="wb-flusher")

    async def shutdown(self) -> None:
        self._stop.set()
        self._wakeup.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self._flush_now()

    async def reset(self) -> None:
        async with self._lock:
            self._dirty.clear()
        metrics.set_value("wb_queue_size", 0)

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
        await cache.cache_set(
            item_id,
            {"id": item_id, "payload": payload, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        async with self._lock:
            self._dirty[item_id] = payload
            queue_size = len(self._dirty)
        metrics.set_value("wb_queue_size", queue_size)
        if queue_size >= WB_FLUSH_BATCH:
            self._wakeup.set()

    async def _flush_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=WB_FLUSH_INTERVAL)
            except asyncio.TimeoutError:
                pass
            self._wakeup.clear()
            await self._flush_now()

    async def _flush_now(self) -> None:
        async with self._lock:
            if not self._dirty:
                metrics.set_value("wb_queue_size", 0)
                return
            batch = list(self._dirty.items())
            self._dirty.clear()
        flushed = await db.bulk_upsert(batch)
        metrics.incr("wb_flushes")
        metrics.incr("wb_flushed_rows", flushed)
        metrics.set_value("wb_queue_size", 0)
