"""Главное меню. Реальная логика лайков/мэтчей подключается в этапах 2–3."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shared.logging import get_logger

from aiogram.types import InputMediaPhoto

from ..api_client import ApiError, CircuitOpenApiError, api_client
from ..embeddings import semantic_interest_boost
from ..filters import TextI18n
from ..fsm import Filters, LikesFeed, RatePeer
from ..i18n import I18n
from ..keyboards import (
    age_preset_kb,
    confirm_delete_kb,
    likes_swipe_kb,
    main_menu_kb,
    match_actions_kb,
    profile_actions_kb,
    rate_peer_kb,
    remove_kb,
    search_city_kb,
    swipe_kb,
    target_gender_kb,
)
from ..photo_proxy import fetch_as_input_file
from ..swipe_publisher import emit_swipe

logger = get_logger(__name__)
router = Router(name="menu")


def _rating_line(i18n: I18n, combined_score: float, primary_score: float) -> str:
    if combined_score > 0:
        return i18n("profile_card_rating", score=combined_score)
    if primary_score > 0:
        profile_part = min(2.5, max(0.0, primary_score * 2.5))
        return i18n("profile_card_rating_basic", score=profile_part)
    return i18n("profile_card_rating", score=combined_score)


@router.message(TextI18n("menu_watch_profiles"))
async def show_feed(message: Message, i18n: I18n) -> None:
    try:
        candidate = await api_client.get_feed(message.from_user.id)
    except CircuitOpenApiError:
        await message.answer(i18n("error_feed_service_unavailable"))
        return
    except (ApiError, Exception):
        logger.exception("feed_fetch_failed")
        candidate = None
    if candidate is None or not candidate.get("profile"):
        await message.answer(i18n("error_feed_fetch_failed"))
        return
    await _render_card(message, candidate, i18n)


async def _render_card(
    message: Message,
    candidate: dict,
    i18n: I18n,
    keyboard_factory=swipe_kb,
) -> None:
    profile = candidate["profile"]
    target_tg = candidate["telegram_id"]
    pct = round(candidate.get("compatibility", 0) * 100)
    interests = ", ".join(profile.get("interests") or []) or None
    combined_score = float(candidate.get("combined_score") or 0.0)
    primary_score = float(candidate.get("primary_score") or 0.0)

    text_lines = [
        i18n("profile_card_name_age", name=profile["name"], age=profile["age"]),
        i18n("profile_card_id", id=target_tg),
        i18n("profile_card_city", city=profile.get("city")) if profile.get("city") else i18n("profile_card_city_not_set"),
        _rating_line(i18n, combined_score, primary_score),
    ]
    text_lines.extend([
        i18n("profile_card_compatibility", pct=pct),
        i18n("profile_card_interests", interests=interests) if interests else i18n("profile_card_interests_empty"),
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
                caption, parse_mode="HTML", reply_markup=keyboard_factory(i18n, target_tg)
            )
            return
        # fallback на единичное фото если получилось скачать <2

    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(
            photo_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard_factory(i18n, target_tg),
        )
    else:
        await message.answer(
            caption, parse_mode="HTML", reply_markup=keyboard_factory(i18n, target_tg)
        )


@router.callback_query(F.data.startswith("swipe:"))
async def on_swipe(call: CallbackQuery, i18n: I18n) -> None:
    parts = call.data.split(":")
    if parts[1] == "stop":
        await call.message.answer(i18n("feed_stop"), reply_markup=main_menu_kb(i18n))
        await call.answer()
        return

    action = parts[1]
    target_tg = int(parts[2])
    await emit_swipe(call.from_user.id, target_tg, action)
    await call.answer(i18n("feed_like_reaction") if action == "like" else i18n("feed_skip_reaction"))

    # Show next card (exclude the profile we just swiped on to avoid race-condition loops)
    try:
        candidate = await api_client.get_feed(call.from_user.id, exclude_telegram_id=target_tg)
    except CircuitOpenApiError:
        await call.message.answer(i18n("error_feed_service_unavailable"))
        return
    except (ApiError, Exception):
        logger.exception("feed_fetch_failed_after_swipe")
        candidate = None
    if candidate is None or not candidate.get("profile"):
        await call.message.answer(i18n("feed_no_profiles"))
        return
    await _render_card(call.message, candidate, i18n)


@router.message(TextI18n("menu_my_profile"))
async def my_profile(message: Message, i18n: I18n) -> None:
    user = await api_client.get_user(message.from_user.id)
    if user is None or user.get("profile") is None:
        await message.answer(i18n("error_no_profile"))
        return
    p = user["profile"]

    # Fetch combined system rating used by ranking-service
    try:
        ratings = await api_client.get_ratings(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("ratings_fetch_failed")
        ratings = None

    combined_score = float((ratings or {}).get("combined_score") or 0.0)
    primary_score = float((ratings or {}).get("primary_score") or 0.0)
    rating_line = _rating_line(i18n, combined_score, primary_score)

    interests = ", ".join(p.get("interests") or []) or None
    text = (
        i18n("profile_card_name_age", name=p["name"], age=p["age"]) + "\n"
        + (i18n("profile_card_city", city=p.get("city")) if p.get("city") else i18n("profile_card_city_not_set")) + "\n"
        + rating_line + "\n"
        + (i18n("profile_card_interests", interests=interests) if interests else i18n("profile_card_interests_empty")) + "\n\n"
        + (p.get("bio") or "")
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
            await message.answer(text, parse_mode="HTML", reply_markup=profile_actions_kb(i18n))
            return
    photo_file = await fetch_as_input_file(photos[0]["url"]) if photos else None
    if photo_file is not None:
        await message.answer_photo(
            photo_file, caption=text, parse_mode="HTML", reply_markup=profile_actions_kb(i18n)
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=profile_actions_kb(i18n))


@router.callback_query(F.data == "profile:delete")
async def on_delete_profile(call: CallbackQuery, i18n: I18n) -> None:
    await call.message.answer(
        i18n("profile_delete_confirm"),
        reply_markup=confirm_delete_kb(i18n),
    )
    await call.answer()


@router.callback_query(F.data == "profile:delete:confirm")
async def on_delete_profile_confirm(call: CallbackQuery, i18n: I18n) -> None:
    try:
        await api_client.delete_user(call.from_user.id)
    except ApiError:
        logger.exception("delete_user_failed")
        await call.message.answer(i18n("error_delete_profile_failed"))
        await call.answer()
        return
    await call.message.answer(
        i18n("profile_deleted"),
        reply_markup=remove_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "profile:delete:cancel")
async def on_delete_profile_cancel(call: CallbackQuery, i18n: I18n) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(i18n("profile_delete_cancelled"))
    await call.answer()


@router.message(TextI18n("menu_filters"))
async def filters_entry(message: Message, state: FSMContext, i18n: I18n) -> None:
    user = await api_client.get_user(message.from_user.id)
    prefs = (user or {}).get("preferences") or {}
    search_city = prefs.get("search_city")
    city_label = search_city if search_city else "любой" if i18n.lang == "ru" else "any"
    await message.answer(
        i18n(
            "filters_current",
            target_gender=prefs.get("target_gender", "—"),
            age_min=prefs.get("age_min", "—"),
            age_max=prefs.get("age_max", "—"),
            city_label=city_label,
        ),
        reply_markup=target_gender_kb(i18n),
    )
    await state.set_state(Filters.target_gender)


@router.callback_query(Filters.target_gender, F.data.startswith("tgender:"))
async def filters_target(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    target = call.data.split(":", 1)[1]
    await state.update_data(target_gender=target)
    await call.message.answer(i18n("filters_age_min_prompt"), reply_markup=age_preset_kb(i18n))
    await state.set_state(Filters.age_min)
    await call.answer()


@router.callback_query(Filters.age_min, F.data.startswith("age:"))
async def filters_age_preset(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    parts = call.data.split(":")
    if parts[1] == "custom":
        await call.message.answer(i18n("filters_age_min_prompt"))
        await call.answer()
        return
    age_min, age_max = int(parts[1]), int(parts[2])
    await state.update_data(age_min=age_min, age_max=age_max)
    await call.message.answer(i18n("filters_choose_search_city"), reply_markup=search_city_kb(i18n))
    await state.set_state(Filters.search_city)
    await call.answer()


@router.message(Filters.age_min, F.text)
async def filters_age_min_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        age_min = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("filters_enter_number"))
        return
    if age_min < 18 or age_min > 100:
        await message.answer(i18n("filters_age_out_of_range"))
        return
    await state.update_data(age_min=age_min)
    await message.answer(i18n("filters_age_max_prompt"))
    await state.set_state(Filters.age_max)


@router.message(Filters.age_max, F.text)
async def filters_age_max_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        age_max = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("filters_enter_number"))
        return
    data = await state.get_data()
    if age_max < data["age_min"] or age_max > 100:
        await message.answer(i18n("filters_age_range_invalid", age_min=data["age_min"]))
        return
    await state.update_data(age_max=age_max)
    await message.answer(i18n("filters_choose_search_city"), reply_markup=search_city_kb(i18n))
    await state.set_state(Filters.search_city)


@router.callback_query(Filters.search_city, F.data.startswith("scity:"))
async def filters_search_city(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    choice = call.data.split(":", 1)[1]
    data = await state.get_data()
    if choice == "own":
        user = await api_client.get_user(call.from_user.id)
        profile = (user or {}).get("profile") or {}
        search_city = profile.get("city")
    elif choice == "any":
        search_city = None
    elif choice == "custom":
        await call.message.answer(i18n("filters_enter_custom_city"))
        await state.set_state(Filters.search_city_custom)
        await call.answer()
        return
    else:
        search_city = None
    payload = {
        "target_gender": data["target_gender"],
        "age_min": data["age_min"],
        "age_max": data["age_max"],
        "search_city": search_city,
    }
    try:
        await api_client.upsert_preferences(call.from_user.id, payload)
    except (ApiError, Exception):
        logger.exception("filters_update_failed", telegram_id=call.from_user.id)
        await call.message.answer(i18n("error_save_filters_failed"))
        await call.answer()
        return
    await state.clear()
    await call.message.answer(
        i18n("filters_updated"),
        reply_markup=main_menu_kb(i18n),
    )
    await call.answer()


@router.message(Filters.search_city_custom, F.text)
async def filters_search_city_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    search_city = message.text.strip().lower()
    data = await state.get_data()
    payload = {
        "target_gender": data["target_gender"],
        "age_min": data["age_min"],
        "age_max": data["age_max"],
        "search_city": search_city,
    }
    try:
        await api_client.upsert_preferences(message.from_user.id, payload)
    except (ApiError, Exception):
        logger.exception("filters_update_failed", telegram_id=message.from_user.id)
        await message.answer(i18n("error_save_filters_failed"))
        return
    await state.clear()
    await message.answer(
        i18n("filters_updated"),
        reply_markup=main_menu_kb(i18n),
    )


@router.message(TextI18n("menu_likes"))
async def show_likes(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        likes = await api_client.get_likes(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("likes_fetch_failed")
        likes = []
    if not likes:
        await message.answer(
            i18n("likes_empty"),
            reply_markup=main_menu_kb(i18n),
        )
        return
    await state.set_state(LikesFeed.viewing)
    await state.update_data(likes=likes, index=0)
    await _show_next_like(message, state, i18n)


def _interest_overlap_boost(viewer_interests, candidate_interests) -> float:
    """Deprecated — kept for backward compatibility."""
    return semantic_interest_boost(viewer_interests, candidate_interests)


async def _show_next_like(message: Message, state: FSMContext, i18n: I18n) -> None:
    data = await state.get_data()
    likes = data.get("likes", [])
    index = data.get("index", 0)
    if index >= len(likes):
        await message.answer(
            i18n("likes_no_more"), reply_markup=main_menu_kb(i18n)
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
        await _show_next_like(message, state, i18n)
        return

    # Compute symmetric compatibility
    viewer_interests = (
        (await api_client.get_user(message.from_user.id)).get("profile") or {}
    ).get("interests")
    candidate_interests = user["profile"].get("interests")
    overlap = _interest_overlap_boost(viewer_interests, candidate_interests)
    compatibility = min(1.0, max(0.0, overlap))

    candidate = {
        "telegram_id": target_tg,
        "profile": user["profile"],
        "compatibility": round(compatibility, 4),
        "combined_score": candidate_score,
        # distance removed
        "photos": user.get("photos") or [],
        "primary_score": float(like_item.get("primary_score") or 0),
    }
    await _render_card(message, candidate, i18n, keyboard_factory=likes_swipe_kb)


@router.callback_query(F.data.startswith("likes:"))
async def on_likes_swipe(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    parts = call.data.split(":")
    if parts[1] == "stop":
        await call.message.answer(i18n("feed_stop"), reply_markup=main_menu_kb(i18n))
        await state.clear()
        await call.answer()
        return

    action = parts[1]
    target_tg = int(parts[2])
    await emit_swipe(call.from_user.id, target_tg, action)
    await call.answer(i18n("feed_like_reaction") if action == "like" else i18n("feed_skip_reaction"))

    data = await state.get_data()
    index = data.get("index", 0)
    await state.update_data(index=index + 1)
    await _show_next_like(call.message, state, i18n)


@router.message(TextI18n("menu_matches"))
async def my_matches(message: Message, i18n: I18n) -> None:
    try:
        matches = await api_client.get_matches(message.from_user.id)
    except (ApiError, Exception):
        logger.exception("matches_fetch_failed")
        matches = []

    if not matches:
        await message.answer(
            i18n("matches_empty"), reply_markup=main_menu_kb(i18n)
        )
        return

    import asyncio

    tasks = [
        api_client.get_user(m["partner_telegram_id"]) for m in matches
    ]
    users = await asyncio.gather(*tasks, return_exceptions=True)

    lines = [i18n("matches_title")]
    for i, (m, u) in enumerate(zip(matches, users), start=1):
        if isinstance(u, Exception) or u is None:
            lines.append(f"{i}. {i18n('matches_unknown_user')}")
            continue
        name = (u.get("profile") or {}).get("name", i18n("matches_unknown_user"))
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
            reply_markup=match_actions_kb(i18n, partner_tg),
        )
        lines.pop()

    if lines == [i18n("matches_title")]:
        # All matches rendered as individual messages
        pass
    else:
        await message.answer("\n".join(lines), reply_markup=main_menu_kb(i18n))


@router.message(TextI18n("menu_invite"))
async def invite_friend(message: Message, i18n: I18n) -> None:
    user = await api_client.get_user(message.from_user.id)
    if user is None:
        await message.answer(i18n("error_not_registered"))
        return
    code = user["user"]["referral_code"]
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    await message.answer(
        i18n("invite_text", code=code, link=link),
        parse_mode="HTML",
    )


# ---------- Peer rating handlers ----------


@router.callback_query(F.data.startswith("match:rate:"))
async def on_rate_match(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    parts = call.data.split(":")
    reviewee_tg = int(parts[2])
    user = await api_client.get_user(reviewee_tg)
    name = (user.get("profile") or {}).get("name", i18n("matches_unknown_user")) if user else i18n("matches_unknown_user")
    await state.set_state(RatePeer.choosing_score)
    await state.update_data(reviewee_telegram_id=reviewee_tg)
    await call.message.answer(
        i18n("rate_prompt", name=name),
        reply_markup=rate_peer_kb(i18n, reviewee_tg),
    )
    await call.answer()


def _parse_review_score(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    if value < 1.0 or value > 5.0:
        return None
    scaled = round(value * 10)
    if abs(value * 10 - scaled) > 1e-9:
        return None
    return scaled / 10


@router.callback_query(F.data.startswith("rate:"))
async def on_rate_score(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    parts = call.data.split(":")
    if parts[1] == "cancel":
        await state.clear()
        await call.message.answer(i18n("rate_cancelled"), reply_markup=main_menu_kb(i18n))
        await call.answer()
        return

    score = _parse_review_score(parts[1])
    if score is None:
        await call.message.answer(
            i18n("rate_invalid_range"),
            reply_markup=main_menu_kb(i18n),
        )
        await state.clear()
        await call.answer()
        return
    reviewee_tg = int(parts[2])
    try:
        await api_client.submit_review(call.from_user.id, reviewee_tg, score)
    except ApiError as e:
        logger.exception("review_submit_failed")
        await call.message.answer(
            i18n("error_review_submit_failed", error=e.body), reply_markup=main_menu_kb(i18n)
        )
        await call.answer()
        return

    await state.clear()
    user = await api_client.get_user(reviewee_tg)
    name = (user.get("profile") or {}).get("name", i18n("matches_unknown_user")) if user else i18n("matches_unknown_user")
    await call.message.answer(
        i18n("rate_submitted", name=name, score=score), reply_markup=main_menu_kb(i18n)
    )
    await call.answer()


@router.message(RatePeer.choosing_score, F.text)
async def on_rate_score_text(message: Message, state: FSMContext, i18n: I18n) -> None:
    raw = (message.text or "").strip()
    cancel_words = {"отмена", "cancel", "/cancel"}
    if i18n.lang == "en":
        cancel_words = {"cancel", "/cancel"}
    if raw.lower() in cancel_words:
        await state.clear()
        await message.answer(i18n("rate_cancelled"), reply_markup=main_menu_kb(i18n))
        return

    score = _parse_review_score(raw)
    if score is None:
        await message.answer(i18n("rate_enter_number"))
        return

    data = await state.get_data()
    reviewee_tg = data.get("reviewee_telegram_id")
    if reviewee_tg is None:
        await state.clear()
        await message.answer(i18n("error_review_target_unknown"), reply_markup=main_menu_kb(i18n))
        return

    try:
        await api_client.submit_review(message.from_user.id, int(reviewee_tg), score)
    except ApiError as e:
        logger.exception("review_submit_failed")
        await message.answer(
            i18n("error_review_submit_failed", error=e.body),
            reply_markup=main_menu_kb(i18n),
        )
        await state.clear()
        return

    await state.clear()
    user = await api_client.get_user(int(reviewee_tg))
    name = (user.get("profile") or {}).get("name", i18n("matches_unknown_user")) if user else i18n("matches_unknown_user")
    await message.answer(
        i18n("rate_submitted", name=name, score=score),
        reply_markup=main_menu_kb(i18n),
    )
