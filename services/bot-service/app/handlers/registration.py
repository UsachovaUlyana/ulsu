"""Registration handlers for the Telegram bot."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from aiogram.filters import Command
import structlog

from app.api_client import profile_client
from app.fsm import RegistrationForm
from app.keyboards import (
    get_gender_keyboard,
    get_main_menu_keyboard,
    get_photo_done_keyboard,
    get_target_gender_keyboard,
)

logger = structlog.get_logger(__name__)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command — begin registration process."""
    telegram_id = message.from_user.id
    username = message.from_user.username

    logger.info("user_started_bot", telegram_id=telegram_id, username=username)

    # Check if user already exists
    try:
        await profile_client.create_user(
            telegram_id=telegram_id, username=username
        )
    except Exception as e:
        error_str = str(e).lower()
        # If user already exists (409), continue registration
        if "already exists" not in error_str and "409" not in error_str and "conflict" not in error_str:
            logger.error("failed_to_create_user", telegram_id=telegram_id, error=str(e))
            await message.answer(
                "❌ Произошла ошибка при регистрации. Попробуйте позже."
            )
            return

    # Start registration FSM
    await state.set_state(RegistrationForm.name)
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Давайте заполним вашу анкету. Это займёт пару минут!\n\n"
        "<b>Шаг 1:</b> Как вас зовут?"
    )


@router.message(RegistrationForm.name)
async def process_name(message: Message, state: FSMContext) -> None:
    """Process user's name."""
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("⚠️ Имя должно содержать минимум 2 символа. Введите имя:")
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(RegistrationForm.age)
    await message.answer(
        "📅 <b>Шаг 2:</b> Сколько вам лет?\n\n"
        "Введите число от 18 до 100:"
    )


@router.message(RegistrationForm.age)
async def process_age(message: Message, state: FSMContext) -> None:
    """Process user's age."""
    if not message.text.isdigit():
        await message.answer("⚠️ Возраст должен быть числом. Введите ваш возраст:")
        return

    age = int(message.text)
    if age < 18 or age > 100:
        await message.answer("⚠️ Возраст должен быть от 18 до 100 лет. Введите ваш возраст:")
        return

    await state.update_data(age=age)
    await state.set_state(RegistrationForm.gender)
    await message.answer(
        "⚧ <b>Шаг 3:</b> Укажите ваш пол:",
        reply_markup=get_gender_keyboard(),
    )


@router.callback_query(F.data.startswith("gender:"), RegistrationForm.gender)
async def process_gender(callback: CallbackQuery, state: FSMContext) -> None:
    """Process user's gender selection."""
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await state.set_state(RegistrationForm.city)
    await callback.message.edit_text("✅ Пол выбран!")
    await callback.message.answer(
        "🏙️ <b>Шаг 4:</b> Из какого вы города?"
    )
    await callback.answer()


@router.message(RegistrationForm.city)
async def process_city(message: Message, state: FSMContext) -> None:
    """Process user's city."""
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("⚠️ Введите название города:")
        return

    await state.update_data(city=message.text.strip())
    await state.set_state(RegistrationForm.bio)
    await message.answer(
        "📝 <b>Шаг 5:</b> Расскажите о себе (необязательно)\n\n"
        "Можете написать пару слов о себе или пропустить командой /skip:"
    )


@router.message(RegistrationForm.bio)
async def process_bio(message: Message, state: FSMContext) -> None:
    """Process user's bio."""
    if message.text and message.text.strip().lower() != "/skip":
        if len(message.text) > 500:
            await message.answer(
                "⚠️ Описание слишком длинное (макс. 500 символов). Сократите или пропустите /skip:"
            )
            return
        await state.update_data(bio=message.text.strip())
    else:
        await state.update_data(bio=None)

    await state.set_state(RegistrationForm.interests)
    await message.answer(
        "🎯 <b>Шаг 6:</b> Ваши интересы\n\n"
        "Перечислите через запятую (например: музыка, спорт, кино):\n"
        "Или пропустите /skip:"
    )


@router.message(RegistrationForm.interests)
async def process_interests(message: Message, state: FSMContext) -> None:
    """Process user's interests."""
    if message.text and message.text.strip().lower() != "/skip":
        interests = [i.strip() for i in message.text.split(",") if i.strip()]
        if not interests:
            await message.answer("⚠️ Введите интересы через запятую или пропустите /skip:")
            return
        await state.update_data(interests=interests)
    else:
        await state.update_data(interests=None)

    await state.set_state(RegistrationForm.photos)
    await message.answer(
        "📷 <b>Шаг 7:</b> Загрузите фотографии\n\n"
        "Отправьте от 1 до 5 фотографий.\n"
        "Когда закончите, нажмите кнопку ниже:",
        reply_markup=get_photo_done_keyboard(),
    )


@router.message(RegistrationForm.photos, F.photo)
async def process_photo(message: Message, state: FSMContext) -> None:
    """Process user's uploaded photos during registration."""
    # Get the best quality photo
    photo: PhotoSize = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    photo_bytes = await message.bot.download_file(file.file_path)

    # Store photos temporarily in FSM state
    user_data = await state.get_data()
    photos = user_data.get("photos", [])
    photos.append({
        "bytes": photo_bytes,
        "filename": f"photo_{len(photos) + 1}.jpg",
    })

    # Limit to 5 photos
    if len(photos) >= 5:
        await state.update_data(photos=photos)
        await message.answer(
            "✅ Загружено 5 фото (максимум).\n"
            "Нажмите кнопку для завершения или удалите лишние и начните заново."
        )
        return

    await state.update_data(photos=photos)
    await message.answer(
        f"✅ Фото {len(photos)} загружено.\n"
        "Можете отправить ещё или нажмите 'Завершить загрузку фото'."
    )


@router.callback_query(F.data == "photos:done", RegistrationForm.photos)
async def finish_photos(callback: CallbackQuery, state: FSMContext) -> None:
    """Finish photo upload and proceed to preferences."""
    user_data = await state.get_data()
    photos = user_data.get("photos", [])

    if not photos:
        await callback.message.answer("⚠️ Загрузите хотя бы одну фотографию!")
        await callback.answer()
        return

    # Upload photos to Profile Service
    telegram_id = callback.from_user.id
    for photo in photos:
        try:
            await profile_client.upload_photo(
                telegram_id=telegram_id,
                photo_bytes=photo["bytes"],
                filename=photo["filename"],
            )
        except Exception as e:
            logger.error("photo_upload_failed", error=str(e))
            await callback.message.answer(
                f"❌ Ошибка при загрузке фото: {str(e)}"
            )
            await callback.answer()
            return

    await callback.message.edit_text("✅ Фотографии загружены!")
    await state.set_state(RegistrationForm.target_gender)
    await callback.message.answer(
        "🔍 <b>Шаг 8:</b> Кого вы ищете?",
        reply_markup=get_target_gender_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("target_gender:"), RegistrationForm.target_gender)
async def process_target_gender(callback: CallbackQuery, state: FSMContext) -> None:
    """Process target gender preference."""
    target_gender = callback.data.split(":")[1]
    await state.update_data(target_gender=target_gender)
    await state.set_state(RegistrationForm.age_min)
    await callback.message.edit_text("✅ Предпочтения по полу выбраны!")
    await callback.message.answer(
        "📅 <b>Минимальный возраст</b> собеседника (18-100):"
    )
    await callback.answer()


@router.message(RegistrationForm.age_min)
async def process_age_min(message: Message, state: FSMContext) -> None:
    """Process minimum age preference."""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число от 18 до 100:")
        return

    age_min = int(message.text)
    if age_min < 18 or age_min > 100:
        await message.answer("⚠️ Возраст должен быть от 18 до 100. Введите минимальный возраст:")
        return

    await state.update_data(age_min=age_min)
    await state.set_state(RegistrationForm.age_max)
    await message.answer(
        "📅 <b>Максимальный возраст</b> собеседника (18-100):"
    )


@router.message(RegistrationForm.age_max)
async def process_age_max(message: Message, state: FSMContext) -> None:
    """Process maximum age preference."""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число от 18 до 100:")
        return

    age_max = int(message.text)
    if age_max < 18 or age_max > 100:
        await message.answer("⚠️ Возраст должен быть от 18 до 100. Введите максимальный возраст:")
        return

    user_data = await state.get_data()
    age_min = user_data.get("age_min", 18)

    if age_max < age_min:
        await message.answer("⚠️ Максимальный возраст не может быть меньше минимального. Введите снова:")
        return

    await state.update_data(age_max=age_max)
    await state.set_state(RegistrationForm.search_city)
    await message.answer(
        "🏙️ <b>Город поиска</b> (оставьте пустым для любого города)\n\n"
        "Введите город или пропустите /skip:"
    )


@router.message(RegistrationForm.search_city)
async def process_search_city(message: Message, state: FSMContext) -> None:
    """Process search city preference and finalize registration."""
    search_city = message.text.strip() if message.text and message.text.strip().lower() != "/skip" else None

    # Save preferences
    await state.update_data(search_city=search_city)
    user_data = await state.get_data()

    telegram_id = message.from_user.id

    # Update profile with basic info
    profile_data = {
        "name": user_data.get("name"),
        "age": user_data.get("age"),
        "gender": user_data.get("gender"),
        "city": user_data.get("city"),
        "bio": user_data.get("bio"),
        "interests": user_data.get("interests"),
        "is_complete": True,
    }

    try:
        await profile_client.update_profile(telegram_id, profile_data)
    except Exception as e:
        logger.error("profile_update_failed", error=str(e))
        await message.answer("❌ Ошибка при сохранении анкеты. Попробуйте /start заново.")
        await state.clear()
        return

    # Update preferences
    preferences = {
        "target_gender": user_data.get("target_gender"),
        "age_min": user_data.get("age_min"),
        "age_max": user_data.get("age_max"),
        "city": user_data.get("search_city"),
    }

    try:
        await profile_client.update_preferences(telegram_id, preferences)
    except Exception as e:
        logger.error("preferences_update_failed", error=str(e))
        await message.answer("❌ Ошибка при сохранении предпочтений. Попробуйте /start заново.")
        await state.clear()
        return

    # Registration complete!
    await state.clear()
    await message.answer(
        "🎉 <b>Анкета заполнена!</b>\n\n"
        "Теперь вы можете искать пары и просматривать анкеты.\n\n"
        "Используйте меню для навигации:",
        reply_markup=get_main_menu_keyboard(),
    )

    logger.info("registration_complete", telegram_id=telegram_id)
