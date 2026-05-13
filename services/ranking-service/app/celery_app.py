from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from shared.logging import configure_logging

from .config import settings

# Celery is sync; configure structlog the same way as the rest.
configure_logging("ranking-celery", settings.log_level)

celery_app = Celery(
    "ranking",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "recalc-behavioral-15min": {
            "task": "app.tasks.recalc_behavioral_all",
            "schedule": crontab(minute="*/15"),
        },
        "recalc-combined-hourly": {
            "task": "app.tasks.recalc_combined_all",
            "schedule": crontab(minute=0),
        },
    },
)
