"""Consumes swipe_events. On a like, checks for the reverse like and emits a match.

Idempotency:
  - Swipes have a unique (swiper_id, target_id) — duplicate INSERTs raise
    IntegrityError and we skip silently (the event was already processed).
  - Matches have a unique (user1_id, user2_id) with user1<user2 ordering —
    same dedup story.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.events import (
    EXCHANGE_MATCHES,
    EXCHANGE_SWIPES,
    RK_MATCH_CREATED,
    RK_SWIPE_CREATED,
)
from shared.logging import get_logger
from shared.metrics import matches_total, swipes_total
from shared.rabbitmq import RabbitMQConsumer, RabbitMQPublisher

from .config import settings
from .database import SessionLocal
from .models import Match, Swipe

logger = get_logger(__name__)

publisher = RabbitMQPublisher(settings.rabbitmq_url)


async def _resolve_user_id(session: AsyncSession, telegram_id: int) -> int | None:
    """The bot publishes telegram_ids; we need internal user.id from the users table."""
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"),
        {"tid": telegram_id},
    )
    row = res.first()
    return row[0] if row else None


async def _resolve_telegram_id(session: AsyncSession, user_id: int) -> int | None:
    res = await session.execute(
        text("SELECT telegram_id FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    row = res.first()
    return row[0] if row else None


async def handle_swipe_event(payload: dict) -> None:
    swiper_tid = int(payload["swiper_telegram_id"])
    target_tid = int(payload["target_telegram_id"])
    action = payload["action"]

    if action not in {"like", "skip"}:
        logger.warning("swipe_unknown_action", action=action)
        return
    if swiper_tid == target_tid:
        return

    swipes_total.labels(action=action).inc()

    async with SessionLocal() as session:
        swiper_id = await _resolve_user_id(session, swiper_tid)
        target_id = await _resolve_user_id(session, target_tid)
        if swiper_id is None or target_id is None:
            logger.warning(
                "swipe_user_unknown", swiper_tid=swiper_tid, target_tid=target_tid
            )
            return

        try:
            session.add(
                Swipe(swiper_id=swiper_id, target_id=target_id, action=action)
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("swipe_duplicate", swiper_id=swiper_id, target_id=target_id)
            return

        if action != "like":
            return

        # Look for reverse like
        reverse = (
            await session.execute(
                select(Swipe).where(
                    Swipe.swiper_id == target_id,
                    Swipe.target_id == swiper_id,
                    Swipe.action == "like",
                )
            )
        ).scalar_one_or_none()

        if reverse is None:
            return

        u1, u2 = sorted((swiper_id, target_id))
        try:
            session.add(Match(user1_id=u1, user2_id=u2))
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("match_duplicate", u1=u1, u2=u2)
            return

        matches_total.inc()
        u1_tid = await _resolve_telegram_id(session, u1)
        u2_tid = await _resolve_telegram_id(session, u2)

        await publisher.publish(
            EXCHANGE_MATCHES,
            RK_MATCH_CREATED,
            {
                "user1_id": u1,
                "user2_id": u2,
                "user1_telegram_id": u1_tid,
                "user2_telegram_id": u2_tid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("match_created", u1=u1, u2=u2)


def make_consumer() -> RabbitMQConsumer:
    return RabbitMQConsumer(
        url=settings.rabbitmq_url,
        exchange=EXCHANGE_SWIPES,
        queue_name="matching.swipe_events",
        routing_keys=[RK_SWIPE_CREATED],
        handler=handle_swipe_event,
    )
