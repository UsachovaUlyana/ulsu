from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.metrics import metrics
from app.models import Base, Item


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/cachebench",
)
SEED_ITEMS = int(os.getenv("SEED_ITEMS", "10000"))
PAYLOAD_SIZE = int(os.getenv("SEED_PAYLOAD_SIZE", "256"))

engine = create_async_engine(DATABASE_URL, pool_size=40, max_overflow=20, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_if_empty() -> None:
    async with SessionLocal() as s:
        count = (await s.execute(text("SELECT COUNT(*) FROM items"))).scalar_one()
        if count >= SEED_ITEMS:
            return
        now = datetime.now(timezone.utc)
        base_payload = "x" * PAYLOAD_SIZE
        rows = [
            {"id": i, "payload": f"{base_payload}-{i}", "updated_at": now}
            for i in range(1, SEED_ITEMS + 1)
        ]
        chunk = 1000
        for start in range(0, len(rows), chunk):
            batch = rows[start : start + chunk]
            stmt = pg_insert(Item).values(batch)
            stmt = stmt.on_conflict_do_nothing(index_elements=[Item.id])
            await s.execute(stmt)
        await s.commit()


async def fetch_item(item_id: int) -> dict | None:
    metrics.incr("db_reads")
    async with SessionLocal() as s:
        row = (await s.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "payload": row.payload,
            "updated_at": row.updated_at.isoformat(),
        }


async def upsert_item(item_id: int, payload: str) -> None:
    metrics.incr("db_writes")
    now = datetime.now(timezone.utc)
    async with SessionLocal() as s:
        stmt = pg_insert(Item).values(id=item_id, payload=payload, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Item.id],
            set_={"payload": stmt.excluded.payload, "updated_at": stmt.excluded.updated_at},
        )
        await s.execute(stmt)
        await s.commit()


async def bulk_upsert(items: Iterable[tuple[int, str]]) -> int:
    rows = [
        {"id": item_id, "payload": payload, "updated_at": datetime.now(timezone.utc)}
        for item_id, payload in items
    ]
    if not rows:
        return 0
    metrics.incr("db_writes")
    async with SessionLocal() as s:
        stmt = pg_insert(Item).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Item.id],
            set_={"payload": stmt.excluded.payload, "updated_at": stmt.excluded.updated_at},
        )
        await s.execute(stmt)
        await s.commit()
    return len(rows)
