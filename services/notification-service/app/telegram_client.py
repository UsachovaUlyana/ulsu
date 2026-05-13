from __future__ import annotations

import aiohttp

from shared.logging import get_logger

from .config import settings

logger = get_logger(__name__)


class TelegramClient:
    BASE = "https://api.telegram.org"

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "HTML"
    ) -> bool:
        session = await self.session()
        url = f"{self.BASE}/bot{settings.telegram_bot_token}/sendMessage"
        try:
            async with session.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
            ) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    logger.warning(
                        "tg_send_failed", chat_id=chat_id, status=resp.status, body=body[:200]
                    )
                return ok
        except Exception:
            logger.exception("tg_send_error", chat_id=chat_id)
            return False


client = TelegramClient()
