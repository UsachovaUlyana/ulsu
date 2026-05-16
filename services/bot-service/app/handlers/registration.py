"""Пошаговая регистрация (FSM)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shared.logging import get_logger

from ..api_client import ApiError, CircuitOpenApiError, api_client
from ..fsm import Registration
from ..i18n import I18n
from ..i18n_middleware import set_user_language
from ..keyboards import (
    age_preset_kb,
    gender_kb,
    language_kb,
    main_menu_kb,
    photos_done_kb,
    remove_kb,
    search_city_kb,
    target_gender_kb,
)

logger = get_logger(__name__)
router = Router(name="registration")


# ---------------------------- /start ----------------------------


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, command: CommandObject, state: FSMContext, i18n: I18n) -> None:
    payload = (command.args or "").strip()
    referral_code: str | None = None
    if payload.startswith("ref_"):
        referral_code = payload[4:][:16]

    await _begin_or_resume(message, state, referral_code, i18n)


@router.message(CommandStart())
async def start_plain(message: Message, state: FSMContext, i18n: I18n) -> None:
    await _begin_or_resume(message, state, referral_code=None, i18n=i18n)


async def _begin_or_resume(
    message: Message, state: FSMContext, referral_code: str | None, i18n: I18n
) -> None:
    try:
        user = await api_client.get_user(message.from_user.id)
    except CircuitOpenApiError:
        await message.answer(i18n("error_profile_service_unavailable"))
        return
    except (ApiError, Exception):
        logger.exception("profile_lookup_failed", telegram_id=message.from_user.id)
        await message.answer(i18n("error_profile_service_request_failed"))
        return
    if user is None:
        try:
            await api_client.create_user(
                message.from_user.id,
                message.from_user.username,
                referral_code_used=referral_code,
            )
        except CircuitOpenApiError:
            await message.answer(i18n("error_create_profile_unavailable"))
            return
        except (ApiError, Exception):
            logger.exception("create_user_failed", telegram_id=message.from_user.id)
            await message.answer(i18n("error_create_profile_failed"))
            return
        await state.update_data(referral_code=referral_code)
        await message.answer(
            i18n("start_greeting"),
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
        try:
            await api_client.apply_referral(referral_code, message.from_user.id)
        except (ApiError, Exception):
            logger.exception(
                "apply_referral_failed",
                telegram_id=message.from_user.id,
                referral_code=referral_code,
            )

    if user.get("profile") is None:
        await message.answer(
            i18n("start_resume_registration"),
            reply_markup=remove_kb(),
        )
        await state.set_state(Registration.name)
        return

    await message.answer(
        i18n("start_welcome_back"),
        reply_markup=main_menu_kb(i18n),
    )


# ---------------------------- Name ----------------------------


@router.message(Registration.name, F.text)
async def reg_name(message: Message, state: FSMContext, i18n: I18n) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(i18n("reg_name_too_short"))
        return
    await state.update_data(name=name[:64])
    await message.answer(i18n("reg_enter_age"))
    await state.set_state(Registration.age)


# ---------------------------- Age ----------------------------


@router.message(Registration.age, F.text)
async def reg_age(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("reg_age_invalid_number"))
        return
    if age < 18 or age > 100:
        await message.answer(i18n("reg_age_out_of_range"))
        return
    await state.update_data(age=age)
    await message.answer(i18n("reg_choose_gender"), reply_markup=gender_kb(i18n))
    await state.set_state(Registration.gender)


# ---------------------------- Gender ----------------------------


@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def reg_gender(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    gender = call.data.split(":", 1)[1]
    await state.update_data(gender=gender)
    await call.message.answer(i18n("reg_enter_city"))
    await state.set_state(Registration.city)
    await call.answer()


# ---------------------------- City ----------------------------


@router.message(Registration.city, F.text)
async def reg_city(message: Message, state: FSMContext, i18n: I18n) -> None:
    city = (message.text or "").strip()[:64]
    if city:
        city = city.lower()
    await state.update_data(city=city or None)
    await message.answer(
        i18n("reg_enter_bio"),
        reply_markup=remove_kb(),
    )
    await state.set_state(Registration.bio)


# ---------------------------- Bio ----------------------------


@router.message(Registration.bio, F.text)
async def reg_bio(message: Message, state: FSMContext, i18n: I18n) -> None:
    text = (message.text or "").strip()
    skip_words = {"пропустить", "skip", "/skip"}
    if i18n.lang == "en":
        skip_words = {"skip", "/skip"}
    bio = None if text.lower() in skip_words else text[:2000]
    await state.update_data(bio=bio)
    await message.answer(i18n("reg_enter_interests"))
    await state.set_state(Registration.interests)


# ---------------------------- Interests ----------------------------


@router.message(Registration.interests, F.text)
async def reg_interests(message: Message, state: FSMContext, i18n: I18n) -> None:
    raw = (message.text or "").strip()
    skip_words = {"пропустить", "skip", "/skip"}
    if i18n.lang == "en":
        skip_words = {"skip", "/skip"}
    if raw.lower() in skip_words:
        interests: list[str] = []
    else:
        interests = [
            part.strip().lower()[:32]
            for part in raw.split(",")
            if part.strip()
        ][:20]
    sent = await message.answer(
        i18n("reg_send_photos"),
        reply_markup=photos_done_kb(i18n, 0),
    )
    await state.update_data(interests=interests, photos=[], photos_kb_msg_id=sent.message_id)
    await state.set_state(Registration.photos)


# ---------------------------- Photos ----------------------------


async def _refresh_photos_counter(
    message: Message, bot: Bot, kb_msg_id: int | None, count: int, i18n: I18n
) -> None:
    """Edit the kbd-message in-place so the counter updates without a new bubble."""
    if kb_msg_id is None:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=kb_msg_id,
            reply_markup=photos_done_kb(i18n, count),
        )
    except Exception:
        # Telegram throws "message is not modified" if nothing changed; ignore.
        pass


@router.message(Registration.photos, F.photo)
async def reg_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    i18n: I18n,
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
    await _refresh_photos_counter(message, bot, kb_msg_id, len(photos), i18n)

    if overflow:
        await message.answer(
            i18n("reg_photos_overflow", accepted=len(accepted), overflow=overflow)
        )


@router.callback_query(Registration.photos, F.data == "photos:done")
async def reg_photos_done(call: CallbackQuery, state: FSMContext, bot: Bot, i18n: I18n) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])
    if not photos:
        await call.answer(i18n("reg_photos_required"), show_alert=True)
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
        # lat/lon removed — city-only filtering
    }
    try:
        await api_client.upsert_profile(telegram_id, profile_payload)
    except CircuitOpenApiError:
        await call.message.answer(i18n("error_save_profile_unavailable"))
        await call.answer()
        return
    except (ApiError, Exception):
        logger.exception("profile_upsert_failed", telegram_id=telegram_id)
        await call.message.answer(i18n("error_save_profile_failed"))
        await call.answer()
        return

    uploaded = 0
    for file_id in photos:
        try:
            tg_file = await bot.get_file(file_id)
            buf = await bot.download_file(tg_file.file_path)
            await api_client.upload_photo(telegram_id, buf.read())
            uploaded += 1
        except Exception:
            logger.exception("photo_upload_failed", file_id=file_id)
    if uploaded == 0:
        await call.message.answer(i18n("error_upload_photos_failed"))
        await call.answer()
        return

    await call.message.answer(i18n("reg_choose_target_gender"), reply_markup=target_gender_kb(i18n))
    await state.set_state(Registration.pref_target_gender)
    await call.answer()


# ---------------------------- Preferences ----------------------------


@router.callback_query(Registration.pref_target_gender, F.data.startswith("tgender:"))
async def reg_pref_target(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    target = call.data.split(":", 1)[1]
    await state.update_data(pref_target=target)
    await call.message.answer(
        i18n("reg_choose_age_range"),
        reply_markup=age_preset_kb(i18n),
    )
    await state.set_state(Registration.pref_age_min)
    await call.answer()


@router.callback_query(Registration.pref_age_min, F.data.startswith("age:"))
async def reg_pref_age_preset(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    parts = call.data.split(":")
    if parts[1] == "custom":
        await call.message.answer(i18n("reg_enter_age_min"))
        # Stay in pref_age_min state, expecting text
        await call.answer()
        return
    age_min, age_max = int(parts[1]), int(parts[2])
    await state.update_data(pref_age_min=age_min, pref_age_max=age_max)
    await call.message.answer(i18n("reg_choose_search_city"), reply_markup=search_city_kb(i18n))
    await state.set_state(Registration.pref_search_city)
    await call.answer()


@router.message(Registration.pref_age_min, F.text)
async def reg_pref_age_min_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        age_min = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("reg_enter_number"))
        return
    if age_min < 18 or age_min > 100:
        await message.answer(i18n("reg_age_out_of_range"))
        return
    await state.update_data(pref_age_min=age_min)
    await message.answer(i18n("reg_enter_age_max"))
    await state.set_state(Registration.pref_age_max)


@router.message(Registration.pref_age_max, F.text)
async def reg_pref_age_max_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    try:
        age_max = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("reg_enter_number"))
        return
    data = await state.get_data()
    age_min = data["pref_age_min"]
    if age_max < age_min or age_max > 100:
        await message.answer(i18n("reg_age_max_invalid", age_min=age_min))
        return
    await state.update_data(pref_age_max=age_max)
    await message.answer(i18n("reg_choose_search_city"), reply_markup=search_city_kb(i18n))
    await state.set_state(Registration.pref_search_city)


@router.callback_query(Registration.pref_search_city, F.data.startswith("scity:"))
async def reg_pref_search_city(call: CallbackQuery, state: FSMContext, i18n: I18n) -> None:
    choice = call.data.split(":", 1)[1]
    data = await state.get_data()
    if choice == "own":
        search_city = data.get("city")
    elif choice == "any":
        search_city = None
    elif choice == "custom":
        await call.message.answer(i18n("reg_enter_custom_city"))
        await state.set_state(Registration.pref_search_city_custom)
        await call.answer()
        return
    else:
        search_city = None
    await state.update_data(search_city=search_city)
    await _complete_registration(call.from_user.id, call.message, state, i18n)
    await call.answer()


@router.message(Registration.pref_search_city_custom, F.text)
async def reg_pref_search_city_custom(message: Message, state: FSMContext, i18n: I18n) -> None:
    search_city = message.text.strip().lower()
    await state.update_data(search_city=search_city)
    await _complete_registration(message.from_user.id, message, state, i18n)


async def _complete_registration(telegram_id: int, message: Message, state: FSMContext, i18n: I18n) -> None:
    data = await state.get_data()
    payload = {
        "target_gender": data["pref_target"],
        "age_min": data["pref_age_min"],
        "age_max": data["pref_age_max"],
        "search_city": data.get("search_city"),
    }
    try:
        await api_client.upsert_preferences(telegram_id, payload)
    except CircuitOpenApiError:
        await message.answer(i18n("error_save_preferences_unavailable"))
        return
    except (ApiError, Exception):
        logger.exception("preferences_upsert_failed", telegram_id=telegram_id)
        await message.answer(i18n("error_save_preferences_failed"))
        return

    # Применяем реферальный код только после полной регистрации анкеты.
    referral_code = data.get("referral_code")
    if referral_code:
        try:
            await api_client.apply_referral(referral_code, telegram_id)
        except (ApiError, Exception):
            logger.exception(
                "apply_referral_failed",
                telegram_id=telegram_id,
                referral_code=referral_code,
            )

    await state.clear()
    await message.answer(
        i18n("reg_complete"),
        reply_markup=main_menu_kb(i18n),
    )


# ---------------------------- /lang ----------------------------


@router.message(Command("lang"))
async def cmd_lang(message: Message, i18n: I18n) -> None:
    await message.answer(i18n("lang_prompt"), reply_markup=language_kb())


@router.callback_query(F.data.startswith("lang:"))
async def callback_set_lang(call: CallbackQuery, bot: Bot, i18n: I18n) -> None:
    lang = call.data.split(":", 1)[1]
    set_user_language(call.from_user.id, lang)
    new_i18n = I18n(lang)
    # Remove old keyboard so the client doesn't keep stale buttons
    await call.message.answer(
        new_i18n("lang_set") if lang == "ru" else new_i18n("lang_set_en"),
        reply_markup=remove_kb(),
    )
    # Send main menu with the new language keyboard
    await call.message.answer(
        new_i18n("menu_title"),
        reply_markup=main_menu_kb(new_i18n),
    )
    await call.answer()


# ---------------------------- /menu fallback ----------------------------


@router.message(Command("menu"))
async def cmd_menu(message: Message, i18n: I18n) -> None:
    await message.answer(i18n("menu_title"), reply_markup=main_menu_kb(i18n))
