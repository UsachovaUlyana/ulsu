"""Menu handlers for the Telegram bot."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
import structlog

from app.keyboards import (
    get_main_menu_keyboard,
    get_settings_keyboard,
)

logger = structlog.get_logger(__name__)

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Show main menu."""
    await message.answer(
        "📱 <b>Главное меню</b>",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:back")
async def back_to_menu(callback: CallbackQuery) -> None:
    """Return to main menu."""
    await callback.message.edit_text(
        "📱 <b>Главное меню</b>",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:feed")
async def open_feed(callback: CallbackQuery) -> None:
    """Open feed/look at profiles."""
    await callback.message.edit_text(
        "👀 <b>Просмотр анкет</b>\n\n"
        "Функция в разработке. Скоро вы сможете смотреть анкеты других пользователей!",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:my_profile")
async def view_my_profile(callback: CallbackQuery) -> None:
    """View user's own profile."""
    await callback.message.edit_text(
        "👤 <b>Моя анкета</b>\n\n"
        "Функция в разработке. Скоро вы сможете просматривать и редактировать свою анкету!",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def open_settings(callback: CallbackQuery) -> None:
    """Open settings menu."""
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=get_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:edit_profile")
async def edit_profile(callback: CallbackQuery) -> None:
    """Edit profile — placeholder."""
    await callback.message.edit_text(
        "✏️ <b>Редактирование анкеты</b>\n\n"
        "Функция в разработке. Скоро вы сможете изменить данные своей анкеты!",
        reply_markup=get_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:edit_preferences")
async def edit_preferences(callback: CallbackQuery) -> None:
    """Edit preferences — placeholder."""
    await callback.message.edit_text(
        "🔍 <b>Настройка предпочтений</b>\n\n"
        "Функция в разработке. Скоро вы сможете изменить предпочтения поиска!",
        reply_markup=get_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("swipe:"))
async def handle_swipe(callback: CallbackQuery) -> None:
    """Handle swipe action (like/skip)."""
    action = callback.data.split(":")[1]
    
    if action == "like":
        await callback.answer("❤️ Лайк отправлен!", show_alert=False)
    else:
        await callback.answer("👎 Пропущено", show_alert=False)
    
    # TODO: Send swipe event to RabbitMQ for Matching Service
    logger.info("swipe_action", user_id=callback.from_user.id, action=action)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Show help message."""
    await message.answer(
        "ℹ️ <b>Доступные команды:</b>\n\n"
        "/start — Начать регистрацию\n"
        "/menu — Главное меню\n"
        "/help — Эта справка\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Нажмите /start для регистрации\n"
        "2. Заполните анкету по шагам\n"
        "3. Используйте меню для навигации"
    )
