from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from redis.asyncio import Redis

from shared.logging import configure_logging, get_logger

from .api_client import api_client
from .config import settings
from .handlers import menu, registration
from .i18n_middleware import I18nMiddleware
from .middlewares import AlbumMiddleware, LoggingMiddleware
from .swipe_publisher import publisher as swipe_publisher

configure_logging("bot-service", settings.log_level)
logger = get_logger(__name__)


async def main() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = RedisStorage(redis=redis)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(I18nMiddleware())
    dp.message.middleware(AlbumMiddleware())

    dp.include_router(registration.router)
    dp.include_router(menu.router)

    await swipe_publisher.connect()

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать / Start"),
            BotCommand(command="menu", description="Главное меню / Main menu"),
            BotCommand(command="lang", description="Сменить язык / Change language"),
        ]
    )
    me = await bot.get_me()
    logger.info("bot_started", username=me.username)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await swipe_publisher.close()
        await api_client.close()
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
