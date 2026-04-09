"""Middleware for logging and metrics."""

from typing import Any, Callable, Dict, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
import structlog

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging all updates."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        """Log update before processing."""
        if isinstance(event, Message):
            logger.info(
                "message_received",
                user_id=event.from_user.id,
                username=event.from_user.username,
                text=event.text,
            )
        elif isinstance(event, CallbackQuery):
            logger.info(
                "callback_received",
                user_id=event.from_user.id,
                username=event.from_user.username,
                data=event.data,
            )

        try:
            result = await handler(event, data)
            return result
        except Exception as e:
            logger.error(
                "handler_error",
                error=str(e),
                user_id=event.from_user.id,
                exc_info=True,
            )
            raise
