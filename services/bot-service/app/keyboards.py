"""Telegram inline keyboards for bot interaction."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_gender_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for gender selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
                InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
            ],
            [
                InlineKeyboardButton(text="🌐 Другой", callback_data="gender:other"),
            ],
        ]
    )


def get_target_gender_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for target gender selection (search preferences)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужчин", callback_data="target_gender:male"),
                InlineKeyboardButton(text="👩 Женщин", callback_data="target_gender:female"),
            ],
            [
                InlineKeyboardButton(text="🌐 Всех", callback_data="target_gender:any"),
            ],
        ]
    )


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard after registration."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👀 Смотреть анкеты", callback_data="menu:feed"),
            ],
            [
                InlineKeyboardButton(text="👤 Моя анкета", callback_data="menu:my_profile"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
            ],
        ]
    )


def get_swipe_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for swiping on profiles."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data="swipe:like"),
                InlineKeyboardButton(text="👎 Пропустить", callback_data="swipe:skip"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu:back"),
            ],
        ]
    )


def get_photo_done_keyboard() -> InlineKeyboardMarkup:
    """Keyboard to signal photo upload is complete."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Завершить загрузку фото", callback_data="photos:done"),
            ],
        ]
    )


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for settings menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="settings:edit_profile"),
            ],
            [
                InlineKeyboardButton(text="🔍 Изменить предпочтения", callback_data="settings:edit_preferences"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu:back"),
            ],
        ]
    )
