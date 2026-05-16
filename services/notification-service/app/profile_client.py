"""Read-only HTTP client for profile-service with circuit breaker."""

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

_breaker = CircuitBreaker(
    service="profile",
    failure_threshold=settings.circuit_failure_threshold,
    open_timeout_seconds=settings.circuit_open_timeout_seconds,
    half_open_max_calls=settings.circuit_half_open_max_calls,
    on_open=lambda svc: circuit_open_total.labels(service=svc).inc(),
    on_short_circuit=lambda svc: circuit_short_circuit_total.labels(service=svc).inc(),
    on_half_open=lambda svc: circuit_half_open_total.labels(service=svc).inc(),
)


async def get_user(telegram_id: int) -> dict | None:
    try:
        execution = await _breaker.before_call()
    except CircuitBreakerOpenError:
        return None

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.profile_client_timeout_seconds)
        ) as session:
            async with session.get(
                f"{settings.profile_service_url}/api/v1/users/{telegram_id}"
            ) as resp:
                if resp.status >= 500:
                    await _breaker.record_failure(
                        execution, reason=f"http_{resp.status}"
                    )
                    return None
                await _breaker.record_success(execution)
                if resp.status != 200:
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        await _breaker.record_failure(execution, reason=e.__class__.__name__)
        logger.exception("profile_lookup_failed", telegram_id=telegram_id)
        return None
    except Exception:
        logger.exception("profile_lookup_failed", telegram_id=telegram_id)
        return None
