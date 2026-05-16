from __future__ import annotations

import asyncio

from prometheus_client import start_http_server

from shared.logging import configure_logging, get_logger

from .config import settings
from .consumer import make_consumer, make_like_consumer
from .telegram_client import client as tg_client

configure_logging("notification-service", settings.log_level)
logger = get_logger(__name__)


async def main() -> None:
    # Expose Prometheus metrics on a small HTTP server (no FastAPI here).
    start_http_server(settings.metrics_port)
    logger.info("notification_metrics_started", port=settings.metrics_port)

    match_consumer = make_consumer()
    like_consumer = make_like_consumer()
    try:
        await asyncio.gather(
            match_consumer.run(),
            like_consumer.run(),
        )
    finally:
        await tg_client.close()


if __name__ == "__main__":
    asyncio.run(main())
