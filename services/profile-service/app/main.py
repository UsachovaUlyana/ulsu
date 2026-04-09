"""Profile Service — entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
import structlog

from app.config import settings
from app.database import init_db, close_db
from app.routes import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger = structlog.get_logger(__name__)
    logger.info("profile_service_starting", port=8001)

    # Initialize database tables
    await init_db()
    logger.info("database_initialized")

    yield

    # Shutdown
    await close_db()
    logger.info("profile_service_stopped")


# Initialize structured logging
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

# Create FastAPI application
app = FastAPI(
    title="Profile Service",
    description="Service for managing user profiles, photos, and preferences",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(users_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "profile-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
