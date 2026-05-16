"""Главное меню. Реальная логика лайков/мэтчей подключается в этапах 2–3."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shared.logging import get_logger

from aiogram.types import InputMediaPhoto

from ..api_client import ApiError, api_client
from ..fsm import Filters, LikesFeed, RatePeer
from ..keyboards import (
    age_preset_kb,
    confirm_delete_kb,
    likes_swipe_kb,
    main_menu_kb,
    match_actions_kb,
    profile_actions_kb,
    rate_peer_kb,
    remove_kb,
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


async def _render_card(
    message: Message,
    candidate: dict,
    keyboard_factory=swipe_kb,
) -> None:
    profile = candidate["profile"]
    target_tg = candidate["telegram_id"]
    pct = round(candidate.get("compatibility", 0) * 100)
    interests = ", ".join(profile.get("interests") or []) or "—"

    peer_rating = candidate.get("peer_rating") or {}
    peer_avg = peer_rating.get("peer_avg")
    peer_count = peer_rating.get("peer_count", 0)

    text_lines = [
        f"<b>{profile['name']}, {profile['age']}</b>",
        f"🆔 ID: {target_tg}",
        f"📍 {profile.get('city') or 'не указан'}",
    ]
    if peer_avg is not None and peer_count > 0:
        text_lines.append(f"⭐ Рейтинг: {peer_avg:.1f} ({peer_count} оценок)")
    else:
        text_lines.append("⭐ Нет оценок")
    text_lines.extend([
        f"💯 Совместимость: {pct}%",
        f"🎯 Интересы: {interests}",
    ])
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
                caption, parse_mode="HTML", reply_markup=keyboard_factory(target_tg)
            )
            return
        # fallback на единичное фото если получилось скачать <2

    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(
            photo_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard_factory(target_tg),
        )
    else:
        await message.answer(
            caption, parse_mode="HTML", reply_markup=keyboard_factory(target_tg)
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

    # Show next card (exclude the profile we just swiped on to avoid race-condition loops)
    try:
        candidate = await api_client.get_feed(call.from_user.id, exclude_telegram_id=target_tg)
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

    # Fetch peer rating summary
    try:
        peer_summary = await api_client.get_peer_summary(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("peer_summary_fetch_failed")
        peer_summary = None

    peer_avg = (peer_summary or {}).get("peer_avg")
    peer_count = (peer_summary or {}).get("peer_count", 0)

    if peer_avg is not None and peer_count > 0:
        rating_line = f"⭐ Рейтинг: {peer_avg:.1f} ({peer_count} оценок)"
    else:
        rating_line = "⭐ Нет оценок"

    text = (
        f"<b>{p['name']}, {p['age']}</b>\n"
        f"📍 {p.get('city') or 'не указан'}\n"
        f"{rating_line}\n"
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
            await message.answer(text, parse_mode="HTML", reply_markup=profile_actions_kb())
            return
    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(
            photo_file, caption=text, parse_mode="HTML", reply_markup=profile_actions_kb()
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=profile_actions_kb())


@router.callback_query(F.data == "profile:delete")
async def on_delete_profile(call: CallbackQuery) -> None:
    await call.message.answer(
        "Ты точно хочешь удалить свою анкету? Это действие необратимо.",
        reply_markup=confirm_delete_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "profile:delete:confirm")
async def on_delete_profile_confirm(call: CallbackQuery) -> None:
    try:
        await api_client.delete_user(call.from_user.id)
    except ApiError:
        logger.exception("delete_user_failed")
        await call.message.answer("Не удалось удалить анкету. Попробуй позже.")
        await call.answer()
        return
    await call.message.answer(
        "Анкета удалена. Возвращайся, когда захочешь! 👋",
        reply_markup=remove_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "profile:delete:cancel")
async def on_delete_profile_cancel(call: CallbackQuery) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("Окей, оставляем всё как есть.")
    await call.answer()


@router.message(F.text == "⚙️ Фильтры")
async def filters_entry(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user(message.from_user.id)
    prefs = (user or {}).get("preferences") or {}
    await message.answer(
        "Текущие фильтры:\n"
        f"• Кого ищу: {prefs.get('target_gender', '—')}\n"
        f"• Возраст: {prefs.get('age_min', '—')}–{prefs.get('age_max', '—')}\n"
        "\n"
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
    data = await state.get_data()
    payload = {
        "target_gender": data["target_gender"],
        "age_min": age_min,
        "age_max": age_max,
    }
    await api_client.upsert_preferences(call.from_user.id, payload)
    await state.clear()
    await call.message.answer(
        "✅ Фильтры обновлены. Лента переформирована.",
        reply_markup=main_menu_kb(),
    )
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
    payload = {
        "target_gender": data["target_gender"],
        "age_min": data["age_min"],
        "age_max": age_max,
    }
    await api_client.upsert_preferences(message.from_user.id, payload)
    await state.clear()
    await message.answer(
        "✅ Фильтры обновлены. Лента переформирована.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "❤️ Кто лайкнул")
async def show_likes(message: Message, state: FSMContext) -> None:
    try:
        likes = await api_client.get_likes(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("likes_fetch_failed")
        likes = []
    if not likes:
        await message.answer(
            "Пока никто не лайкнул твою анкету. Продолжай свайпать!",
            reply_markup=main_menu_kb(),
        )
        return
    await state.set_state(LikesFeed.viewing)
    await state.update_data(likes=likes, index=0)
    await _show_next_like(message, state)


def _interest_overlap_boost(viewer_interests, candidate_interests) -> float:
    if not viewer_interests or not candidate_interests:
        return 0.0
    a = {x.lower() for x in viewer_interests}
    b = {x.lower() for x in candidate_interests}
    overlap = len(a & b)
    if not overlap:
        return 0.0
    return min(0.15, overlap * 0.05)


async def _show_next_like(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    likes = data.get("likes", [])
    index = data.get("index", 0)
    if index >= len(likes):
        await message.answer(
            "Больше никого нет. Возвращайся позже!", reply_markup=main_menu_kb()
        )
        await state.clear()
        return
    like_item = likes[index]
    target_tg = like_item["telegram_id"]
    candidate_score = float(like_item.get("combined_score") or 0.0)
    try:
        user = await api_client.get_user(target_tg)
    except (ApiError, Exception):
        logger.exception("like_user_fetch_failed", target_tg=target_tg)
        user = None
    if user is None or not user.get("profile"):
        await state.update_data(index=index + 1)
        await _show_next_like(message, state)
        return

    # Compute symmetric compatibility
    viewer_ratings = await api_client.get_ratings(message.from_user.id)
    viewer_score = float((viewer_ratings or {}).get("combined_score") or 0.0)
    viewer_interests = (
        (await api_client.get_user(message.from_user.id)).get("profile") or {}
    ).get("interests")
    candidate_interests = user["profile"].get("interests")
    overlap = _interest_overlap_boost(viewer_interests, candidate_interests)
    compatibility = (viewer_score + candidate_score) / 2.0 + overlap
    compatibility = min(1.0, max(0.0, compatibility))

    candidate = {
        "telegram_id": target_tg,
        "profile": user["profile"],
        "compatibility": round(compatibility, 4),
        # distance removed
        "photos": user.get("photos") or [],
        "primary_score": float(like_item.get("primary_score") or 0),
        "peer_rating": {
            "peer_avg": like_item.get("peer_avg"),
            "peer_count": like_item.get("peer_count", 0),
        },
    }
    await _render_card(message, candidate, keyboard_factory=likes_swipe_kb)


@router.callback_query(F.data.startswith("likes:"))
async def on_likes_swipe(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")
    if parts[1] == "stop":
        await call.message.answer("Окей, стопаем.", reply_markup=main_menu_kb())
        await state.clear()
        await call.answer()
        return

    action = parts[1]
    target_tg = int(parts[2])
    await emit_swipe(call.from_user.id, target_tg, action)
    await call.answer("❤️" if action == "like" else "👎")

    data = await state.get_data()
    index = data.get("index", 0)
    await state.update_data(index=index + 1)
    await _show_next_like(call.message, state)


@router.message(F.text == "💌 Мои мэтчи")
async def my_matches(message: Message) -> None:
    try:
        matches = await api_client.get_matches(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("matches_fetch_failed")
        matches = []

    if not matches:
        await message.answer(
            "У тебя пока нет мэтчей. Продолжай свайпать! ❤️", reply_markup=main_menu_kb()
        )
        return

    import asyncio

    tasks = [
        api_client.get_user(m["partner_telegram_id"]) for m in matches
    ]
    users = await asyncio.gather(*tasks, return_exceptions=True)

    lines = ["💌 Твои мэтчи:\n"]
    for i, (m, u) in enumerate(zip(matches, users), start=1):
        if isinstance(u, Exception) or u is None:
            lines.append(f"{i}. Неизвестный пользователь")
            continue
        name = (u.get("profile") or {}).get("name", "Кто-то")
        username = (u.get("user") or {}).get("username")
        partner_tg = m.get("partner_telegram_id")
        if username:
            lines.append(f"{i}. {name} (@{username})")
        else:
            lines.append(f"{i}. {name}")
        # Send each match as a separate message with action buttons
        match_text = lines[-1]
        await message.answer(
            match_text,
            reply_markup=match_actions_kb(partner_tg),
        )
        lines.pop()

    if lines == ["💌 Твои мэтчи:\n"]:
        # All matches rendered as individual messages
        pass
    else:
        await message.answer("\n".join(lines), reply_markup=main_menu_kb())


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


# ---------- Peer rating handlers ----------


@router.callback_query(F.data.startswith("match:rate:"))
async def on_rate_match(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")
    reviewee_tg = int(parts[2])
    user = await api_client.get_user(reviewee_tg)
    name = (user.get("profile") or {}).get("name", "пользователя") if user else "пользователя"
    await state.set_state(RatePeer.choosing_score)
    await state.update_data(reviewee_telegram_id=reviewee_tg)
    await call.message.answer(
        f"Оцени общение с {name}:",
        reply_markup=rate_peer_kb(reviewee_tg),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate:"))
async def on_rate_score(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")
    if parts[1] == "cancel":
        await state.clear()
        await call.message.answer("Оценка отменена.", reply_markup=main_menu_kb())
        await call.answer()
        return

    score = int(parts[1])
    reviewee_tg = int(parts[2])
    try:
        await api_client.submit_review(call.from_user.id, reviewee_tg, score)
    except ApiError as e:
        logger.exception("review_submit_failed")
        await call.message.answer(
            f"Не удалось сохранить оценку: {e.body}", reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await state.clear()
    user = await api_client.get_user(reviewee_tg)
    name = (user.get("profile") or {}).get("name", "пользователю") if user else "пользователю"
    await call.message.answer(
        f"Ты поставил(а) {name} {'⭐' * score}", reply_markup=main_menu_kb()
    )
    await call.answer()
