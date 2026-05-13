from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging, get_logger
from shared.metrics import setup_fastapi_metrics

from .config import settings
from .consumers import run_all_consumers
from .routes import router

configure_logging("ranking-service", settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_all_consumers(), name="ranking-consumers")
    logger.info("ranking_service_started")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("ranking_service_stopped")


app = FastAPI(title="Dating Ranking Service", lifespan=lifespan)
app.include_router(router)
setup_fastapi_metrics(app)
