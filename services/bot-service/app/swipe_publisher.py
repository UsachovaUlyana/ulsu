from __future__ import annotations

from datetime import datetime, timezone

from shared.events import EXCHANGE_SWIPES, RK_SWIPE_CREATED
from shared.rabbitmq import RabbitMQPublisher

from .config import settings

publisher = RabbitMQPublisher(settings.rabbitmq_url)


async def emit_swipe(swiper_telegram_id: int, target_telegram_id: int, action: str) -> None:
    await publisher.publish(
        EXCHANGE_SWIPES,
        RK_SWIPE_CREATED,
        {
            "swiper_telegram_id": swiper_telegram_id,
            "target_telegram_id": target_telegram_id,
            "action": action,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
