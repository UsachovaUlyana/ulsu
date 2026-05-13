from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging, get_logger
from shared.metrics import setup_fastapi_metrics

from .config import settings
from .events_publisher import publisher
from .routes import router

configure_logging("profile-service", settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await publisher.connect()
    logger.info("profile_service_started")
    try:
        yield
    finally:
        await publisher.close()
        logger.info("profile_service_stopped")


app = FastAPI(title="Dating Profile Service", lifespan=lifespan)
app.include_router(router)
setup_fastapi_metrics(app)
