"""Простой JSON-based i18n без внешних зависимостей."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent.parent / "locales"


class I18n:
    def __init__(self, lang: str = "ru") -> None:
        self.lang = lang if lang in ("ru", "en") else "ru"
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        path = _LOCALES_DIR / f"{self.lang}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)

    def get(self, key: str, **kwargs: Any) -> str:
        text = self._data.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                pass
        return text

    def __call__(self, key: str, **kwargs: Any) -> str:
        return self.get(key, **kwargs)


def get_i18n(lang: str | None = None) -> I18n:
    return I18n(lang or "ru")
