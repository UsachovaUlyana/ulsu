from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging, get_logger
from shared.metrics import setup_fastapi_metrics

from .config import settings
from .consumer import make_consumer, publisher
from .routes import router

configure_logging("matching-service", settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await publisher.connect()
    consumer = make_consumer()
    consumer_task = asyncio.create_task(consumer.run(), name="swipe-consumer")
    logger.info("matching_service_started")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        await publisher.close()
        logger.info("matching_service_stopped")


app = FastAPI(title="Dating Matching Service", lifespan=lifespan)
app.include_router(router)
setup_fastapi_metrics(app)
