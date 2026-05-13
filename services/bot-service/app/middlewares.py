from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User

import structlog

from shared.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        bind = {}
        if user:
            bind["telegram_id"] = user.id
            bind["username"] = user.username
        with structlog.contextvars.bound_contextvars(**bind):
            logger.info("update_received", type=event.__class__.__name__)
            return await handler(event, data)


class AlbumMiddleware(BaseMiddleware):
    """Группирует апдейты с одним media_group_id в один вызов handler'а.

    Telegram присылает альбом из N фото пятью отдельными Update'ами с
    одинаковым `media_group_id`. Без группировки бот реагирует на каждое
    фото отдельно — получается спам ответов.

    Алгоритм:
      - первое сообщение из группы запоминаем в буфер, ждём `latency` сек
      - последующие — складываем в тот же буфер и НЕ дёргаем handler
      - после `latency` отдаём весь буфер одним вызовом через data["album"]
    """

    def __init__(self, latency: float = 0.6) -> None:
        self.latency = latency
        self._buffers: dict[str, list[Message]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.media_group_id:
            return await handler(event, data)

        gid = event.media_group_id
        if gid in self._buffers:
            self._buffers[gid].append(event)
            return

        self._buffers[gid] = [event]
        await asyncio.sleep(self.latency)
        album = self._buffers.pop(gid, [event])
        data["album"] = album
        return await handler(event, data)
