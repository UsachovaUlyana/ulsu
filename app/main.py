from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import cache, db
from app.metrics import metrics
from app.strategies import CacheStrategy, get_strategy


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("p3.app")

STRATEGY_NAME = os.getenv("CACHE_STRATEGY", "cache_aside")

_strategy: CacheStrategy | None = None
_started_at: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _strategy, _started_at
    log.info("starting app with CACHE_STRATEGY=%s", STRATEGY_NAME)
    await db.init_schema()
    await db.seed_if_empty()
    _strategy = get_strategy(STRATEGY_NAME)
    await _strategy.startup()
    _started_at = time.time()
    try:
        yield
    finally:
        if _strategy is not None:
            await _strategy.shutdown()


app = FastAPI(title="p3 cache strategies bench", lifespan=lifespan)


class WriteBody(BaseModel):
    payload: str = Field(min_length=1)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "strategy": STRATEGY_NAME, "uptime_s": round(time.time() - _started_at, 1)}


@app.get("/items/{item_id}")
async def read_item(item_id: int) -> dict:
    metrics.incr("requests_total")
    metrics.incr("read_total")
    assert _strategy is not None
    row = await _strategy.get(item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.put("/items/{item_id}")
async def write_item(item_id: int, body: WriteBody) -> dict:
    metrics.incr("requests_total")
    metrics.incr("write_total")
    assert _strategy is not None
    await _strategy.set(item_id, body.payload)
    return {"ok": True}


@app.get("/metrics")
async def get_metrics() -> dict:
    snap = metrics.snapshot()
    info = await cache.redis_info_stats()
    snap["redis_keyspace_hits"] = info["keyspace_hits"]
    snap["redis_keyspace_misses"] = info["keyspace_misses"]
    snap["strategy"] = STRATEGY_NAME
    return snap


@app.post("/admin/reset")
async def admin_reset(flush_cache: bool = True) -> dict:
    metrics.reset()
    if flush_cache:
        await cache.cache_flushdb()
    if _strategy is not None:
        await _strategy.reset()
    return {"ok": True}


@app.post("/admin/wb-flush")
async def admin_wb_flush() -> dict:
    if _strategy is None or _strategy.name != "write_back":
        raise HTTPException(status_code=400, detail="not in write_back mode")
    await _strategy._flush_now()  # type: ignore[attr-defined]
    return {"ok": True, "wb_queue_size": metrics.snapshot()["wb_queue_size"]}
