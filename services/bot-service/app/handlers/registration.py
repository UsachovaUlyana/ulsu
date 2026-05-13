"""Pошаговая регистрация (FSM)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shared.logging import get_logger

from ..api_client import api_client
from ..fsm import Registration
from ..keyboards import (
    age_preset_kb,
    distance_kb,
    gender_kb,
    location_request_kb,
    main_menu_kb,
    photos_done_kb,
    remove_kb,
    target_gender_kb,
)

logger = get_logger(__name__)
router = Router(name="registration")


# ---------------------------- /start ----------------------------


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, command: CommandObject, state: FSMContext) -> None:
    payload = (command.args or "").strip()
    referral_code: str | None = None
    if payload.startswith("ref_"):
        referral_code = payload[4:][:16]

    await _begin_or_resume(message, state, referral_code)


@router.message(CommandStart())
async def start_plain(message: Message, state: FSMContext) -> None:
    await _begin_or_resume(message, state, referral_code=None)


async def _begin_or_resume(
    message: Message, state: FSMContext, referral_code: str | None
) -> None:
    user = await api_client.get_user(message.from_user.id)
    if user is None:
        await api_client.create_user(
            message.from_user.id,
            message.from_user.username,
            referral_code_used=referral_code,
        )
        await state.update_data(referral_code=referral_code)
        await message.answer(
            "Привет! 👋 Давай заполним анкету.\n\nКак тебя зовут?",
            reply_markup=remove_kb(),
        )
        await state.set_state(Registration.name)
        return

    # Existing user: try to apply referral if profile already complete and not yet referred
    if (
        referral_code
        and user.get("user", {}).get("referred_by") is None
        and user.get("profile") is not None
    ):
        await api_client.apply_referral(referral_code, message.from_user.id)

    if user.get("profile") is None:
        await message.answer(
            "Ты уже начинал регистрацию, но не закончил. Давай продолжим — как тебя зовут?",
            reply_markup=remove_kb(),
        )
        await state.set_state(Registration.name)
        return

    await message.answer(
        "С возвращением! 🎉",
        reply_markup=main_menu_kb(),
    )


# ---------------------------- Name ----------------------------


@router.message(Registration.name, F.text)
async def reg_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Минимум 2 символа.")
        return
    await state.update_data(name=name[:64])
    await message.answer("Сколько тебе лет?")
    await state.set_state(Registration.age)


# ---------------------------- Age ----------------------------


@router.message(Registration.age, F.text)
async def reg_age(message: Message, state: FSMContext) -> None:
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer("Введи возраст числом.")
        return
    if age < 18 or age > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    await state.update_data(age=age)
    await message.answer("Твой пол?", reply_markup=gender_kb())
    await state.set_state(Registration.gender)


# ---------------------------- Gender ----------------------------


@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def reg_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":", 1)[1]
    await state.update_data(gender=gender)
    await call.message.answer("Из какого ты города?")
    await state.set_state(Registration.city)
    await call.answer()


# ---------------------------- City ----------------------------


@router.message(Registration.city, F.text)
async def reg_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()[:64]
    await state.update_data(city=city or None)
    await message.answer(
        "Отправь свою геолокацию, чтобы мы показывали анкеты рядом. "
        "Можешь пропустить — но без неё не сможем считать расстояние.",
        reply_markup=location_request_kb(),
    )
    await state.set_state(Registration.location)


# ---------------------------- Location ----------------------------


@router.message(Registration.location, F.location)
async def reg_location(message: Message, state: FSMContext) -> None:
    await state.update_data(lat=message.location.latitude, lon=message.location.longitude)
    await message.answer(
        "📍 Локация сохранена. Расскажи о себе (или напиши «пропустить»).",
        reply_markup=remove_kb(),
    )
    await state.set_state(Registration.bio)


@router.message(Registration.location, F.text)
async def reg_location_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(lat=None, lon=None)
    await message.answer(
        "Окей, без геолокации. Расскажи о себе (или напиши «пропустить»).",
        reply_markup=remove_kb(),
    )
    await state.set_state(Registration.bio)


# ---------------------------- Bio ----------------------------


@router.message(Registration.bio, F.text)
async def reg_bio(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    bio = None if text.lower() in {"пропустить", "skip", "/skip"} else text[:2000]
    await state.update_data(bio=bio)
    await message.answer(
        "Какие у тебя интересы? Перечисли через запятую "
        "(например: спорт, музыка, путешествия). Или «пропустить»."
    )
    await state.set_state(Registration.interests)


# ---------------------------- Interests ----------------------------


@router.message(Registration.interests, F.text)
async def reg_interests(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.lower() in {"пропустить", "skip", "/skip"}:
        interests: list[str] = []
    else:
        interests = [
            part.strip().lower()[:32]
            for part in raw.split(",")
            if part.strip()
        ][:20]
    sent = await message.answer(
        "Отправь от 1 до 5 фотографий — можно одним альбомом или по одной. "
        "Когда закончишь — нажми «Готово».",
        reply_markup=photos_done_kb(0),
    )
    await state.update_data(interests=interests, photos=[], photos_kb_msg_id=sent.message_id)
    await state.set_state(Registration.photos)


# ---------------------------- Photos ----------------------------


async def _refresh_photos_counter(
    message: Message, bot: Bot, kb_msg_id: int | None, count: int
) -> None:
    """Edit the kbd-message in-place so the counter updates without a new bubble."""
    if kb_msg_id is None:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=kb_msg_id,
            reply_markup=photos_done_kb(count),
        )
    except Exception:
        # Telegram throws "message is not modified" if nothing changed; ignore.
        pass


@router.message(Registration.photos, F.photo)
async def reg_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    album: list[Message] | None = None,
) -> None:
    """Receives either one photo or a whole media-group (album middleware)."""
    data = await state.get_data()
    photos: list[str] = list(data.get("photos", []))
    kb_msg_id = data.get("photos_kb_msg_id")

    incoming = album if album else [message]
    new_ids = [m.photo[-1].file_id for m in incoming if m.photo]

    free = max(0, 5 - len(photos))
    accepted = new_ids[:free]
    overflow = len(new_ids) - len(accepted)
    photos.extend(accepted)

    await state.update_data(photos=photos)
    await _refresh_photos_counter(message, bot, kb_msg_id, len(photos))

    if overflow:
        await message.answer(f"Принял первые {len(accepted)}, лишние {overflow} проигнорировал — лимит 5.")


@router.callback_query(Registration.photos, F.data == "photos:done")
async def reg_photos_done(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])
    if not photos:
        await call.answer("Нужна хотя бы одна фотография!", show_alert=True)
        return

    # Push profile + photos to profile-service
    telegram_id = call.from_user.id
    profile_payload = {
        "name": data["name"],
        "age": data["age"],
        "gender": data["gender"],
        "city": data.get("city"),
        "bio": data.get("bio"),
        "interests": data.get("interests") or None,
        "lat": data.get("lat"),
        "lon": data.get("lon"),
    }
    await api_client.upsert_profile(telegram_id, profile_payload)

    for file_id in photos:
        try:
            tg_file = await bot.get_file(file_id)
            buf = await bot.download_file(tg_file.file_path)
            await api_client.upload_photo(telegram_id, buf.read())
        except Exception:
            logger.exception("photo_upload_failed", file_id=file_id)

    await call.message.answer("Кого ты ищешь?", reply_markup=target_gender_kb())
    await state.set_state(Registration.pref_target_gender)
    await call.answer()


# ---------------------------- Preferences ----------------------------


@router.callback_query(Registration.pref_target_gender, F.data.startswith("tgender:"))
async def reg_pref_target(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.split(":", 1)[1]
    await state.update_data(pref_target=target)
    await call.message.answer(
        "Какой возраст ищешь?",
        reply_markup=age_preset_kb(),
    )
    await state.set_state(Registration.pref_age_min)
    await call.answer()


@router.callback_query(Registration.pref_age_min, F.data.startswith("age:"))
async def reg_pref_age_preset(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")
    if parts[1] == "custom":
        await call.message.answer("Минимальный возраст? (число от 18)")
        # Stay in pref_age_min state, expecting text
        await call.answer()
        return
    age_min, age_max = int(parts[1]), int(parts[2])
    await state.update_data(pref_age_min=age_min, pref_age_max=age_max)
    await call.message.answer(
        f"Окей, ищем {age_min}–{age_max}. Радиус поиска?",
        reply_markup=distance_kb(),
    )
    await state.set_state(Registration.pref_distance)
    await call.answer()


@router.message(Registration.pref_age_min, F.text)
async def reg_pref_age_min_custom(message: Message, state: FSMContext) -> None:
    try:
        age_min = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число.")
        return
    if age_min < 18 or age_min > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    await state.update_data(pref_age_min=age_min)
    await message.answer("Максимальный возраст?")
    await state.set_state(Registration.pref_age_max)


@router.message(Registration.pref_age_max, F.text)
async def reg_pref_age_max_custom(message: Message, state: FSMContext) -> None:
    try:
        age_max = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число.")
        return
    data = await state.get_data()
    age_min = data["pref_age_min"]
    if age_max < age_min or age_max > 100:
        await message.answer(f"Должно быть от {age_min} до 100.")
        return
    await state.update_data(pref_age_max=age_max)
    await message.answer("Радиус поиска?", reply_markup=distance_kb())
    await state.set_state(Registration.pref_distance)


@router.callback_query(Registration.pref_distance, F.data.startswith("dist:"))
async def reg_pref_distance(call: CallbackQuery, state: FSMContext) -> None:
    dist = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    payload = {
        "target_gender": data["pref_target"],
        "age_min": data["pref_age_min"],
        "age_max": data["pref_age_max"],
        "max_distance_km": dist or None,
    }
    await api_client.upsert_preferences(call.from_user.id, payload)

    # Apply referral now (after registration is complete) if there was one in /start
    referral_code = data.get("referral_code")
    if referral_code:
        await api_client.apply_referral(referral_code, call.from_user.id)

    await state.clear()
    await call.message.answer(
        "✅ Анкета готова! Можешь начинать знакомиться.",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ---------------------------- /menu fallback ----------------------------


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_kb())
