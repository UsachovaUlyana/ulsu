"""RabbitMQ-консюмеры в ranking-service.

profile_events  → перерасчёт L1 (через Celery .delay)
swipe_events    → запись в activity_log + (опционально) триггер L2
match_events    → запись активности обоих участников
referral_events → triggers combined recalc on demand
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text

from shared.events import (
    EXCHANGE_MATCHES,
    EXCHANGE_PROFILES,
    EXCHANGE_REFERRALS,
    EXCHANGE_SWIPES,
    RK_MATCH_CREATED,
    RK_PROFILE_UPDATED,
    RK_REFERRAL_APPLIED,
    RK_SWIPE_CREATED,
)
from shared.logging import get_logger
from shared.rabbitmq import RabbitMQConsumer

from .config import settings
from .database import AsyncSessionLocal

logger = get_logger(__name__)


def _enqueue_primary(user_id: int) -> None:
    # Delayed import — Celery app shouldn't be imported eagerly during ASGI init
    from .tasks import recalc_primary_for_user

    recalc_primary_for_user.delay(user_id)


async def _resolve_user_id_async(telegram_id: int) -> int | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id FROM users WHERE telegram_id = :tid"),
            {"tid": telegram_id},
        )
        row = res.first()
        return row[0] if row else None


async def _log_activity(user_id: int, event_type: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO activity_log (user_id, event_type, hour_of_day) "
                "VALUES (:uid, :etype, :hour)"
            ),
            {
                "uid": user_id,
                "etype": event_type,
                "hour": datetime.now(timezone.utc).hour,
            },
        )
        await session.commit()


async def handle_profile_updated(payload: dict) -> None:
    user_id = int(payload["user_id"])
    _enqueue_primary(user_id)
    # Invalidate this user's feed cache — preferences may have changed
    from .feed_service import get_redis

    await get_redis().delete(f"feed:{user_id}")


async def handle_swipe(payload: dict) -> None:
    swiper_tid = int(payload["swiper_telegram_id"])
    swiper_id = await _resolve_user_id_async(swiper_tid)
    if swiper_id is None:
        return
    await _log_activity(swiper_id, "swipe")


async def handle_match(payload: dict) -> None:
    for tid_field in ("user1_telegram_id", "user2_telegram_id"):
        tid = payload.get(tid_field)
        if tid is None:
            continue
        uid = await _resolve_user_id_async(int(tid))
        if uid is not None:
            await _log_activity(uid, "match")


async def handle_referral(payload: dict) -> None:
    """Bonuses are accumulated in the `referrals` table; the L3 recalc reads them.
    Trigger an immediate combined recalc so the boost shows up before the hourly cron."""
    from .tasks import recalc_combined_all
    recalc_combined_all.delay()


def make_consumers() -> list[RabbitMQConsumer]:
    return [
        RabbitMQConsumer(
            url=settings.rabbitmq_url,
            exchange=EXCHANGE_PROFILES,
            queue_name="ranking.profile_events",
            routing_keys=[RK_PROFILE_UPDATED],
            handler=handle_profile_updated,
        ),
        RabbitMQConsumer(
            url=settings.rabbitmq_url,
            exchange=EXCHANGE_SWIPES,
            queue_name="ranking.swipe_events",
            routing_keys=[RK_SWIPE_CREATED],
            handler=handle_swipe,
        ),
        RabbitMQConsumer(
            url=settings.rabbitmq_url,
            exchange=EXCHANGE_MATCHES,
            queue_name="ranking.match_events",
            routing_keys=[RK_MATCH_CREATED],
            handler=handle_match,
        ),
        RabbitMQConsumer(
            url=settings.rabbitmq_url,
            exchange=EXCHANGE_REFERRALS,
            queue_name="ranking.referral_events",
            routing_keys=[RK_REFERRAL_APPLIED],
            handler=handle_referral,
        ),
    ]


async def run_all_consumers() -> None:
    consumers = make_consumers()
    await asyncio.gather(*(c.run() for c in consumers))
