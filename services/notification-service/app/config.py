from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    telegram_bot_token: str
    profile_service_url: str = "http://profile-service:8001"
    profile_client_timeout_seconds: float = 5.0
    circuit_failure_threshold: int = 5
    circuit_open_timeout_seconds: int = 30
    circuit_half_open_max_calls: int = 1
    metrics_port: int = 8004


settings = Settings()
