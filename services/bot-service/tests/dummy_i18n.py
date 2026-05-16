from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_RU_TRANSLATIONS: dict[str, str] = {}
_jaon_path = _ROOT / "locales" / "ru.json"
if _jaon_path.exists():
    with open(_jaon_path, encoding="utf-8") as _f:
        _RU_TRANSLATIONS = json.load(_f)


class DummyI18n:
    """Test helper that mimics app.i18n.I18n using Russian strings."""

    def __init__(self, lang: str = "ru") -> None:
        self.lang = lang

    def get(self, key: str, **kwargs) -> str:
        text = _RU_TRANSLATIONS.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                pass
        return text

    def __call__(self, key: str, **kwargs) -> str:
        return self.get(key, **kwargs)
