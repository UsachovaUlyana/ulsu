from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
                InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
            ],
            [InlineKeyboardButton(text="🌈 Другой", callback_data="gender:other")],
        ]
    )


def target_gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Парней", callback_data="tgender:male"),
                InlineKeyboardButton(text="👩 Девушек", callback_data="tgender:female"),
            ],
            [InlineKeyboardButton(text="✨ Любых", callback_data="tgender:any")],
        ]
    )


def location_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="Пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def photos_done_kb(count: int = 0) -> InlineKeyboardMarkup:
    label = f"✅ Готово ({count}/5)" if count else "✅ Готово"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="photos:done")]
        ]
    )


def age_preset_kb() -> InlineKeyboardMarkup:
    """Возрастные пресеты для поиска. Последняя кнопка — ввести руками."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="18–25", callback_data="age:18:25"),
                InlineKeyboardButton(text="22–30", callback_data="age:22:30"),
                InlineKeyboardButton(text="25–35", callback_data="age:25:35"),
            ],
            [
                InlineKeyboardButton(text="30–45", callback_data="age:30:45"),
                InlineKeyboardButton(text="40–60", callback_data="age:40:60"),
                InlineKeyboardButton(text="∞ Любой", callback_data="age:18:99"),
            ],
            [InlineKeyboardButton(text="✏️ Свой диапазон", callback_data="age:custom")],
        ]
    )


def distance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 км", callback_data="dist:5"),
                InlineKeyboardButton(text="10 км", callback_data="dist:10"),
                InlineKeyboardButton(text="25 км", callback_data="dist:25"),
            ],
            [
                InlineKeyboardButton(text="50 км", callback_data="dist:50"),
                InlineKeyboardButton(text="100 км", callback_data="dist:100"),
                InlineKeyboardButton(text="∞ Любая", callback_data="dist:0"),
            ],
        ]
    )


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔥 Смотреть анкеты")],
            [
                KeyboardButton(text="👤 Моя анкета"),
                KeyboardButton(text="⚙️ Фильтры"),
            ],
            [
                KeyboardButton(text="💌 Мои мэтчи"),
                KeyboardButton(text="🎁 Пригласить друга"),
            ],
        ],
        resize_keyboard=True,
    )


def swipe_kb(target_telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Лайк", callback_data=f"swipe:like:{target_telegram_id}"
                ),
                InlineKeyboardButton(
                    text="👎 Скип", callback_data=f"swipe:skip:{target_telegram_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Стоп", callback_data="swipe:stop"
                )
            ],
        ]
    )
