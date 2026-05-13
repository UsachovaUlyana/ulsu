from __future__ import annotations

from shared.events import EXCHANGE_MATCHES, RK_MATCH_CREATED
from shared.logging import get_logger
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

    await tg_client.send_message(u1_tid, msg_for_u1)
    await tg_client.send_message(u2_tid, msg_for_u2)
    logger.info(
        "match_notified", u1=u1_tid, u2=u2_tid, category=category, topics=len(topics)
    )


def make_consumer() -> RabbitMQConsumer:
    return RabbitMQConsumer(
        url=settings.rabbitmq_url,
        exchange=EXCHANGE_MATCHES,
        queue_name="notification.match_events",
        routing_keys=[RK_MATCH_CREATED],
        handler=handle_match_event,
    )
