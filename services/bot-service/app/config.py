from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    telegram_bot_token: str
    profile_service_url: str = "http://profile-service:8001"
    ranking_service_url: str = "http://ranking-service:8002"
    matching_service_url: str = "http://matching-service:8003"
    redis_url: str = "redis://redis:6379/0"
    swipe_rate_limit_per_min: int = 30


settings = Settings()
