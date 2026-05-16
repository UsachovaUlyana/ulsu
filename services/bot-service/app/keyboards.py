from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from .i18n import I18n


def gender_kb(i18n: I18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n("btn_male"), callback_data="gender:male"),
                InlineKeyboardButton(text=i18n("btn_female"), callback_data="gender:female"),
            ],
            [InlineKeyboardButton(text=i18n("btn_other_gender"), callback_data="gender:other")],
        ]
    )


def target_gender_kb(i18n: I18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n("btn_target_male"), callback_data="tgender:male"),
                InlineKeyboardButton(text=i18n("btn_target_female"), callback_data="tgender:female"),
            ],
            [InlineKeyboardButton(text=i18n("btn_target_any"), callback_data="tgender:any")],
        ]
    )


def search_city_kb(i18n: I18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n("btn_city_own"), callback_data="scity:own"),
                InlineKeyboardButton(text=i18n("btn_city_any"), callback_data="scity:any"),
            ],
            [
                InlineKeyboardButton(text=i18n("btn_city_custom"), callback_data="scity:custom"),
            ],
        ]
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def photos_done_kb(i18n: I18n, count: int = 0) -> InlineKeyboardMarkup:
    label = i18n("btn_done_with_count", count=count) if count else i18n("btn_done")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="photos:done")]
        ]
    )


def age_preset_kb(i18n: I18n) -> InlineKeyboardMarkup:
    """Возрастные пресеты для поиска. Последняя кнопка — ввести руками."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n("btn_age_18_25"), callback_data="age:18:25"),
                InlineKeyboardButton(text=i18n("btn_age_22_30"), callback_data="age:22:30"),
                InlineKeyboardButton(text=i18n("btn_age_25_35"), callback_data="age:25:35"),
            ],
            [
                InlineKeyboardButton(text=i18n("btn_age_30_45"), callback_data="age:30:45"),
                InlineKeyboardButton(text=i18n("btn_age_40_60"), callback_data="age:40:60"),
                InlineKeyboardButton(text=i18n("btn_age_any"), callback_data="age:18:99"),
            ],
            [InlineKeyboardButton(text=i18n("btn_age_custom"), callback_data="age:custom")],
        ]
    )


def main_menu_kb(i18n: I18n) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=i18n("menu_watch_profiles"))],
            [
                KeyboardButton(text=i18n("menu_my_profile")),
                KeyboardButton(text=i18n("menu_filters")),
            ],
            [
                KeyboardButton(text=i18n("menu_likes")),
                KeyboardButton(text=i18n("menu_matches")),
            ],
            [
                KeyboardButton(text=i18n("menu_invite")),
            ],
        ],
        resize_keyboard=True,
    )


def profile_actions_kb(i18n: I18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n("btn_delete_profile"), callback_data="profile:delete"
                )
            ]
        ]
    )


def confirm_delete_kb(i18n: I18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n("btn_confirm_delete"), callback_data="profile:delete:confirm"
                ),
                InlineKeyboardButton(
                    text=i18n("btn_cancel"), callback_data="profile:delete:cancel"
                ),
            ]
        ]
    )


def likes_swipe_kb(i18n: I18n, target_telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n("btn_like"), callback_data=f"likes:like:{target_telegram_id}"
                ),
                InlineKeyboardButton(
                    text=i18n("btn_skip"), callback_data=f"likes:skip:{target_telegram_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n("btn_stop"), callback_data="likes:stop"
                )
            ],
        ]
    )


def swipe_kb(i18n: I18n, target_telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n("btn_like"), callback_data=f"swipe:like:{target_telegram_id}"
                ),
                InlineKeyboardButton(
                    text=i18n("btn_skip"), callback_data=f"swipe:skip:{target_telegram_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n("btn_stop"), callback_data="swipe:stop"
                )
            ],
        ]
    )


def match_actions_kb(i18n: I18n, partner_telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n("btn_rate"), callback_data=f"match:rate:{partner_telegram_id}"
                )
            ]
        ]
    )


def rate_peer_kb(i18n: I18n, reviewee_telegram_id: int) -> InlineKeyboardMarkup:
    quick_scores = ["5.0", "4.8", "4.5", "4.0", "3.5"]
    buttons = [
        InlineKeyboardButton(
            text=f"{score} ⭐", callback_data=f"rate:{score}:{reviewee_telegram_id}"
        )
        for score in quick_scores
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons[:3],
            buttons[3:],
            [InlineKeyboardButton(text=i18n("btn_cancel"), callback_data="rate:cancel")],
        ]
    )


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )
