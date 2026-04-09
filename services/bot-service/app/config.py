"""Configuration for Bot Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Telegram Bot
    telegram_bot_token: str

    # Service URLs
    profile_service_url: str = "http://profile-service:8001"
    ranking_service_url: str = "http://ranking-service:8002"

    # Redis (for FSM storage)
    redis_url: str = "redis://redis:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://dating_user:dating_pass@rabbitmq:5672/"

    # Logging
    log_level: str = "INFO"


settings = Settings()
