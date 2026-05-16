from __future__ import annotations

from shared.events import (
    EXCHANGE_MATCHES,
    EXCHANGE_REFERRALS,
    EXCHANGE_SWIPES,
    RK_LIKE_RECEIVED,
    RK_MATCH_CREATED,
    RK_REFERRAL_APPLIED,
)
from shared.logging import get_logger
from shared.metrics import likes_notified_total, referrals_notified_total
from shared.rabbitmq import RabbitMQConsumer

from .config import settings
from .icebreaker import pick_topics
from .profile_client import get_user
from .telegram_client import client as tg_client

logger = get_logger(__name__)


async def handle_match_event(payload: dict) -> None:
    u1_tid = int(payload["user1_telegram_id"])
    u2_tid = int(payload["user2_telegram_id"])

    u1 = await get_user(u1_tid)
    u2 = await get_user(u2_tid)
    if u1 is None or u2 is None:
        logger.warning("match_user_lookup_failed", u1_tid=u1_tid, u2_tid=u2_tid)
        return

    u1_name = (u1.get("profile") or {}).get("name", "Кто-то")
    u2_name = (u2.get("profile") or {}).get("name", "Кто-то")
    u1_username = (u1.get("user") or {}).get("username")
    u2_username = (u2.get("user") or {}).get("username")
    u1_interests = (u1.get("profile") or {}).get("interests")
    u2_interests = (u2.get("profile") or {}).get("interests")

    topics, category = pick_topics(u1_interests, u2_interests)
    bullets = "\n".join(f"  {i}. {t}" for i, t in enumerate(topics, start=1))

    msg_for_u1 = (
        f"🎉 У вас мэтч с <b>{u2_name}</b>!\n\n"
        f"💡 <i>Темы для начала разговора ({category}):</i>\n{bullets}"
    )
    msg_for_u2 = (
        f"🎉 У вас мэтч с <b>{u1_name}</b>!\n\n"
        f"💡 <i>Темы для начала разговора ({category}):</i>\n{bullets}"
    )

    if u2_username:
        msg_for_u1 += f"\n\n👤 Напиши ему/ей: @{u2_username}"
    if u1_username:
        msg_for_u2 += f"\n\n👤 Напиши ему/ей: @{u1_username}"

    await tg_client.send_message(u1_tid, msg_for_u1)
    await tg_client.send_message(u2_tid, msg_for_u2)
    logger.info(
        "match_notified", u1=u1_tid, u2=u2_tid, category=category, topics=len(topics)
    )


async def handle_like_received(payload: dict) -> None:
    target_tid = int(payload["target_telegram_id"])
    msg = "❤️ Кому-то понравилась твоя анкета! Загляни в бот, чтобы узнать кто."
    await tg_client.send_message(target_tid, msg)
    likes_notified_total.inc()
    logger.info("like_notified", target_tid=target_tid)


async def handle_referral_event(payload: dict) -> None:
    inviter_tid = int(payload["inviter_telegram_id"])
    bonus = float(payload.get("bonus_value", 0.05))
    msg = (
        f"🎉 По твоей реферальной ссылке зарегистрировался новый пользователь!\n"
        f"📈 Тебе начислен бонус к рейтингу: +{bonus:.0%}."
    )
    await tg_client.send_message(inviter_tid, msg)
    referrals_notified_total.inc()
    logger.info("referral_notified", inviter_tid=inviter_tid, bonus=bonus)


def make_consumer() -> RabbitMQConsumer:
    return RabbitMQConsumer(
        url=settings.rabbitmq_url,
        exchange=EXCHANGE_MATCHES,
        queue_name="notification.match_events",
        routing_keys=[RK_MATCH_CREATED],
        handler=handle_match_event,
    )


def make_like_consumer() -> RabbitMQConsumer:
    return RabbitMQConsumer(
        url=settings.rabbitmq_url,
        exchange=EXCHANGE_SWIPES,
        queue_name="notification.like_events",
        routing_keys=[RK_LIKE_RECEIVED],
        handler=handle_like_received,
    )


def make_referral_consumer() -> RabbitMQConsumer:
    return RabbitMQConsumer(
        url=settings.rabbitmq_url,
        exchange=EXCHANGE_REFERRALS,
        queue_name="notification.referral_events",
        routing_keys=[RK_REFERRAL_APPLIED],
        handler=handle_referral_event,
    )
