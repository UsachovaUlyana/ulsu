from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    database_url: str = (
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot"
    )
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    feed_cache_ttl_seconds: int = 1800
    feed_batch_size: int = 10

    # Weights — kept in config for easy tuning
    w_l1_completeness: float = 0.4
    w_l1_photos: float = 0.3
    w_l1_prefs: float = 0.3

    w_l2_likes_received: float = 0.3
    w_l2_like_ratio: float = 0.3
    w_l2_mutual: float = 0.2
    w_l2_dialog: float = 0.1
    w_l2_activity: float = 0.1

    w_combined_l1: float = 0.3
    w_combined_l2: float = 0.6
    w_combined_referral: float = 0.1

    referral_bonus_cap: float = 0.3


settings = Settings()


def sync_database_url() -> str:
    """Celery + sync SQLAlchemy use psycopg2 driver."""
    return settings.database_url.replace("+asyncpg", "+psycopg2")
