"""Pulls photo presigned URLs from profile-service with circuit breaker."""

from __future__ import annotations

import asyncio

import aiohttp

from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from shared.logging import get_logger
from shared.metrics import (
    circuit_half_open_total,
    circuit_open_total,
    circuit_short_circuit_total,
)

from .config import settings

logger = get_logger(__name__)

PROFILE_SERVICE_URL = "http://profile-service:8001"

_breaker = CircuitBreaker(
    service="profile",
    failure_threshold=settings.circuit_failure_threshold,
    open_timeout_seconds=settings.circuit_open_timeout_seconds,
    half_open_max_calls=settings.circuit_half_open_max_calls,
    on_open=lambda svc: circuit_open_total.labels(service=svc).inc(),
    on_short_circuit=lambda svc: circuit_short_circuit_total.labels(service=svc).inc(),
    on_half_open=lambda svc: circuit_half_open_total.labels(service=svc).inc(),
)


async def get_photos(telegram_id: int) -> list[dict]:
    try:
        execution = await _breaker.before_call()
    except CircuitBreakerOpenError:
        logger.debug("photos_short_circuited", telegram_id=telegram_id)
        return []

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.profile_client_timeout_seconds)
        ) as session:
            async with session.get(
                f"{PROFILE_SERVICE_URL}/api/v1/users/{telegram_id}"
            ) as resp:
                if resp.status >= 500:
                    await _breaker.record_failure(
                        execution, reason=f"http_{resp.status}"
                    )
                    return []
                await _breaker.record_success(execution)
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("photos") or []
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        await _breaker.record_failure(execution, reason=e.__class__.__name__)
        logger.warning(
            "photos_fetch_failed",
            telegram_id=telegram_id,
            error=e.__class__.__name__,
        )
        return []
    except Exception:
        logger.exception("photos_fetch_failed", telegram_id=telegram_id)
        return []
