"""Главное меню. Реальная логика лайков/мэтчей подключается в этапах 2–3."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shared.logging import get_logger

from aiogram.types import InputMediaPhoto

from ..api_client import ApiError, api_client
from ..fsm import Filters
from ..keyboards import (
    age_preset_kb,
    distance_kb,
    main_menu_kb,
    swipe_kb,
    target_gender_kb,
)
from ..photo_proxy import fetch_as_input_file
from ..swipe_publisher import emit_swipe

logger = get_logger(__name__)
router = Router(name="menu")


@router.message(F.text == "🔥 Смотреть анкеты")
async def show_feed(message: Message) -> None:
    try:
        candidate = await api_client.get_feed(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("feed_fetch_failed")
        candidate = None
    if candidate is None or not candidate.get("profile"):
        await message.answer(
            "Пока некого показать — попробуй позже или расширь фильтры."
        )
        return
    await _render_card(message, candidate)


async def _render_card(message: Message, candidate: dict) -> None:
    profile = candidate["profile"]
    target_tg = candidate["telegram_id"]
    pct = round(candidate.get("compatibility", 0) * 100)
    distance = candidate.get("distance_km")
    interests = ", ".join(profile.get("interests") or []) or "—"

    text_lines = [
        f"<b>{profile['name']}, {profile['age']}</b>",
        f"📍 {profile.get('city') or 'не указан'}"
        + (f" • {distance:.1f} км" if distance is not None else ""),
        f"💯 Совместимость: {pct}%",
        f"🎯 Интересы: {interests}",
    ]
    bio = profile.get("bio")
    if bio:
        text_lines.append(f"\n{bio}")

    photos = candidate.get("photos") or []
    caption = "\n".join(text_lines)

    # Сначала пытаемся прокачать ВСЕ фото — Telegram нативно покажет их каруселью
    if len(photos) > 1:
        media = []
        for p in photos[:5]:
            f = await fetch_as_input_file(p["url"])
            if f is not None:
                media.append(InputMediaPhoto(media=f))
        if len(media) >= 2:
            await message.answer_media_group(media)
            await message.answer(
                caption, parse_mode="HTML", reply_markup=swipe_kb(target_tg)
            )
            return
        # fallback на единичное фото если получилось скачать <2

    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(
            photo_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=swipe_kb(target_tg),
        )
    else:
        await message.answer(
            caption, parse_mode="HTML", reply_markup=swipe_kb(target_tg)
        )


@router.callback_query(F.data.startswith("swipe:"))
async def on_swipe(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if parts[1] == "stop":
        await call.message.answer("Окей, стопаем.", reply_markup=main_menu_kb())
        await call.answer()
        return

    action = parts[1]
    target_tg = int(parts[2])
    await emit_swipe(call.from_user.id, target_tg, action)
    await call.answer("❤️" if action == "like" else "👎")

    # Show next card
    try:
        candidate = await api_client.get_feed(call.from_user.id)
    except (ApiError, Exception):
        logger.exception("feed_fetch_failed_after_swipe")
        candidate = None
    if candidate is None or not candidate.get("profile"):
        await call.message.answer("Анкеты закончились. Загляни позже!")
        return
    await _render_card(call.message, candidate)


@router.message(F.text == "👤 Моя анкета")
async def my_profile(message: Message) -> None:
    user = await api_client.get_user(message.from_user.id)
    if user is None or user.get("profile") is None:
        await message.answer("У тебя ещё нет анкеты. Нажми /start.")
        return
    p = user["profile"]
    text = (
        f"<b>{p['name']}, {p['age']}</b>\n"
        f"📍 {p.get('city') or 'не указан'}\n"
        f"🎯 Интересы: {', '.join(p.get('interests') or []) or '—'}\n\n"
        f"{p.get('bio') or ''}"
    )
    photos = user.get("photos") or []
    if len(photos) > 1:
        media = []
        for p in photos[:5]:
            f = await fetch_as_input_file(p["url"])
            if f is not None:
                media.append(InputMediaPhoto(media=f))
        if len(media) >= 2:
            await message.answer_media_group(media)
            await message.answer(text, parse_mode="HTML")
            return
    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(photo_file, caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "⚙️ Фильтры")
async def filters_entry(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user(message.from_user.id)
    prefs = (user or {}).get("preferences") or {}
    await message.answer(
        "Текущие фильтры:\n"
        f"• Кого ищу: {prefs.get('target_gender', '—')}\n"
        f"• Возраст: {prefs.get('age_min', '—')}–{prefs.get('age_max', '—')}\n"
        f"• Дистанция: {prefs.get('max_distance_km') or '∞'} км\n\n"
        "Кого ищешь? (выбор перезапишет фильтр)",
        reply_markup=target_gender_kb(),
    )
    await state.set_state(Filters.target_gender)


@router.callback_query(Filters.target_gender, F.data.startswith("tgender:"))
async def filters_target(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.split(":", 1)[1]
    await state.update_data(target_gender=target)
    await call.message.answer("Какой возраст ищешь?", reply_markup=age_preset_kb())
    await state.set_state(Filters.age_min)
    await call.answer()


@router.callback_query(Filters.age_min, F.data.startswith("age:"))
async def filters_age_preset(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")
    if parts[1] == "custom":
        await call.message.answer("Минимальный возраст? (число от 18)")
        await call.answer()
        return
    age_min, age_max = int(parts[1]), int(parts[2])
    await state.update_data(age_min=age_min, age_max=age_max)
    await call.message.answer(
        f"Окей, {age_min}–{age_max}. Радиус поиска?", reply_markup=distance_kb()
    )
    await state.set_state(Filters.distance)
    await call.answer()


@router.message(Filters.age_min, F.text)
async def filters_age_min_custom(message: Message, state: FSMContext) -> None:
    try:
        age_min = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число.")
        return
    if age_min < 18 or age_min > 100:
        await message.answer("Возраст 18–100.")
        return
    await state.update_data(age_min=age_min)
    await message.answer("Максимальный возраст?")
    await state.set_state(Filters.age_max)


@router.message(Filters.age_max, F.text)
async def filters_age_max_custom(message: Message, state: FSMContext) -> None:
    try:
        age_max = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число.")
        return
    data = await state.get_data()
    if age_max < data["age_min"] or age_max > 100:
        await message.answer(f"Должно быть от {data['age_min']} до 100.")
        return
    await state.update_data(age_max=age_max)
    await message.answer("Радиус поиска?", reply_markup=distance_kb())
    await state.set_state(Filters.distance)


@router.callback_query(Filters.distance, F.data.startswith("dist:"))
async def filters_distance(call: CallbackQuery, state: FSMContext) -> None:
    dist = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    payload = {
        "target_gender": data["target_gender"],
        "age_min": data["age_min"],
        "age_max": data["age_max"],
        "max_distance_km": dist or None,
    }
    await api_client.upsert_preferences(call.from_user.id, payload)
    await state.clear()
    await call.message.answer(
        "✅ Фильтры обновлены. Лента переформирована.",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


@router.message(F.text == "💌 Мои мэтчи")
async def my_matches_placeholder(message: Message) -> None:
    await message.answer("Список мэтчей появится после первого взаимного лайка ❤️")


@router.message(F.text == "🎁 Пригласить друга")
async def invite_friend(message: Message) -> None:
    user = await api_client.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала зарегистрируйся: /start")
        return
    code = user["user"]["referral_code"]
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    await message.answer(
        f"Твой реферальный код: <b>{code}</b>\n\n"
        f"Поделись ссылкой: <code>{link}</code>\n\n"
        "Когда друг зарегистрируется по твоей ссылке, оба получите буст в выдаче 🚀",
        parse_mode="HTML",
    )
