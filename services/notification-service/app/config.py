from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    telegram_bot_token: str
    profile_service_url: str = "http://profile-service:8001"
    metrics_port: int = 8004


settings = Settings()
