"""Middleware that injects I18n instance into handler data."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from .i18n import I18n

# Manual language overrides (telegram_id -> lang). Falls back to Telegram's language_code.
_lang_overrides: dict[int, str] = {}


def set_user_language(telegram_id: int, lang: str) -> None:
    _lang_overrides[telegram_id] = lang


def get_user_language(telegram_id: int, fallback: str | None = None) -> str:
    return _lang_overrides.get(telegram_id, fallback or "ru")


class I18nMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None:
            lang = get_user_language(user.id, fallback=user.language_code)
        else:
            lang = "ru"
        # Normalize: only ru/en supported
        if lang not in ("ru", "en"):
            lang = "ru"
        data["i18n"] = I18n(lang)
        return await handler(event, data)
