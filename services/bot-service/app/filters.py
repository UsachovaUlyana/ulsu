"""Custom aiogram filters for i18n-aware handlers."""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message

from .i18n import I18n


class TextI18n(Filter):
    """Matches message.text against the localized string for the given key.

    Falls back to other supported locales so that stale reply keyboards
    (left over from a previous language) still work.
    """

    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(self, message: Message, i18n: I18n) -> bool:
        if message.text == i18n(self.key):
            return True
        # Stale keyboard fallback: check all supported languages
        for lang in ("ru", "en"):
            if lang != i18n.lang and message.text == I18n(lang)(self.key):
                return True
        return False
