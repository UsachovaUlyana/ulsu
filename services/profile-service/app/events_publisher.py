from __future__ import annotations

from shared.events import (
    EXCHANGE_PROFILES,
    EXCHANGE_REFERRALS,
    RK_PROFILE_UPDATED,
    RK_REFERRAL_APPLIED,
)
from shared.rabbitmq import RabbitMQPublisher

from .config import settings

publisher = RabbitMQPublisher(settings.rabbitmq_url)


async def emit_profile_updated(user_id: int, telegram_id: int) -> None:
    await publisher.publish(
        EXCHANGE_PROFILES,
        RK_PROFILE_UPDATED,
        {"user_id": user_id, "telegram_id": telegram_id},
    )


async def emit_referral_applied(
    inviter_id: int, invitee_id: int, bonus_value: float
) -> None:
    await publisher.publish(
        EXCHANGE_REFERRALS,
        RK_REFERRAL_APPLIED,
        {
            "inviter_id": inviter_id,
            "invitee_id": invitee_id,
            "bonus_value": bonus_value,
        },
    )
