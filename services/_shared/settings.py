"""Common BaseSettings pieces shared between services."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    """Subclass me in each service and add service-specific fields."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = "INFO"
    rabbitmq_url: str = "amqp://dating_user:dating_pass@rabbitmq:5672/"
