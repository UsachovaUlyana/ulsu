"""Telegram Bot Service — entry point."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis
import structlog

from app.config import settings
from app.api_client import profile_client
from app.handlers import registration, menu
from app.middlewares import LoggingMiddleware


async def on_startup(dispatcher: Dispatcher, bot: Bot) -> None:
    """Actions on bot startup."""
    logger = structlog.get_logger(__name__)
    logger.info(
        "bot_started",
        bot_username=(await bot.get_me()).username,
    )


async def on_shutdown(dispatcher: Dispatcher, bot: Bot) -> None:
    """Actions on bot shutdown."""
    logger = structlog.get_logger(__name__)
    logger.info("bot_stopped")
    await profile_client.close()


async def main() -> None:
    """Initialize and start the bot."""
    # Configure structured logging
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(__name__)

    # Initialize bot with HTML parse mode by default
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Initialize Redis storage for FSM
    redis = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )
    fsm_storage = RedisStorage(redis=redis)

    # Register startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Include routers
    dp.include_router(registration.router)
    dp.include_router(menu.router)

    # Add middleware
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())

    # Start polling
    try:
        logger.info("starting_polling")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, fsm_storage=fsm_storage)
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.error("polling_error", error=str(e), exc_info=True)
    finally:
        await bot.session.close()
        await redis.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
