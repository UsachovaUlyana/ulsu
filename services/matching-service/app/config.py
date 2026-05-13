from __future__ import annotations

from shared.settings import CommonSettings


class Settings(CommonSettings):
    database_url: str = (
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot"
    )


settings = Settings()
