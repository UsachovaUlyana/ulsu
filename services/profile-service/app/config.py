"""Configuration for Profile Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Database
    database_url: str = "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot"

    # MinIO (S3)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minio_user"
    minio_secret_key: str = "minio_pass"
    minio_bucket: str = "photos"

    # RabbitMQ
    rabbitmq_url: str = "amqp://dating_user:dating_pass@rabbitmq:5672/"

    # Logging
    log_level: str = "INFO"


settings = Settings()
