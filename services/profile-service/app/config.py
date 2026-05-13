from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    database_url: str = (
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot"
    )
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minio_user"
    minio_secret_key: str = "minio_pass"
    minio_bucket: str = "photos"
    minio_secure: bool = False
    presigned_url_ttl_seconds: int = 3600


settings = Settings()
