from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    database_url: str = (
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot"
    )
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Circuit breaker for inter-service calls
    circuit_failure_threshold: int = 5
    circuit_open_timeout_seconds: int = 30
    circuit_half_open_max_calls: int = 1
    profile_client_timeout_seconds: float = 5.0

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

    # L3 (combined) is represented on a public 0..5 scale.
    # Inputs primary/behavioral/peer remain normalized to 0..1.
    combined_profile_part_max: float = 2.5
    combined_behavioral_part_max: float = 0.5
    combined_peer_part_max: float = 1.8
    combined_referral_part_max: float = 0.2
    combined_score_max: float = 5.0

    referral_bonus_cap: float = 0.3
    peer_dampening_threshold: float = 10.0
    peer_prior_mean: float = 3.0
    peer_prior_weight: float = 5.0
    good_review_threshold: float = 4.5


settings = Settings()


def sync_database_url() -> str:
    """Celery + sync SQLAlchemy use psycopg2 driver."""
    return settings.database_url.replace("+asyncpg", "+psycopg2")
