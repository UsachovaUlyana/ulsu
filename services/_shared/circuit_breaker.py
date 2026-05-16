"""Упрощённый Circuit Breaker для межсервисных вызовов."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum

from .logging import get_logger

logger = get_logger(__name__)


class CircuitBreakerOpenError(Exception):
    """Ошибка short-circuit: внешний вызов не выполнялся."""

    def __init__(self, service: str) -> None:
        self.service = service
        super().__init__(f"circuit open for service={service}")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitExecution:
    is_probe: bool = False


class CircuitBreaker:
    def __init__(
        self,
        *,
        service: str,
        failure_threshold: int,
        open_timeout_seconds: float,
        half_open_max_calls: int,
        on_open=None,
        on_short_circuit=None,
        on_half_open=None,
        time_fn=None,
    ) -> None:
        self._service = service
        self._failure_threshold = max(1, int(failure_threshold))
        self._open_timeout_seconds = max(0.1, float(open_timeout_seconds))
        self._half_open_max_calls = max(1, int(half_open_max_calls))
        self._on_open = on_open
        self._on_short_circuit = on_short_circuit
        self._on_half_open = on_half_open
        self._time_fn = time_fn or time.monotonic

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def before_call(self) -> CircuitExecution:
        async with self._lock:
            now = self._time_fn()
            if self._state == CircuitState.OPEN:
                if now - self._opened_at >= self._open_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_flight = 0
                    logger.info("circuit_half_open", service=self._service)
                    if self._on_half_open:
                        self._on_half_open(self._service)
                else:
                    if self._on_short_circuit:
                        self._on_short_circuit(self._service)
                    raise CircuitBreakerOpenError(self._service)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self._half_open_max_calls:
                    if self._on_short_circuit:
                        self._on_short_circuit(self._service)
                    raise CircuitBreakerOpenError(self._service)
                self._half_open_in_flight += 1
                return CircuitExecution(is_probe=True)

            return CircuitExecution(is_probe=False)

    async def record_success(self, execution: CircuitExecution) -> None:
        async with self._lock:
            if execution.is_probe and self._half_open_in_flight > 0:
                self._half_open_in_flight -= 1

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                self._opened_at = 0.0
                self._half_open_in_flight = 0
                logger.info("circuit_closed", service=self._service)
                return

            if self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    async def record_failure(self, execution: CircuitExecution, *, reason: str) -> None:
        async with self._lock:
            if execution.is_probe and self._half_open_in_flight > 0:
                self._half_open_in_flight -= 1

            if self._state == CircuitState.HALF_OPEN:
                self._open(reason=reason)
                return

            if self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._failure_threshold:
                    self._open(reason=reason)

    def _open(self, *, reason: str) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._time_fn()
        self._consecutive_failures = 0
        self._half_open_in_flight = 0
        logger.warning("circuit_opened", service=self._service, reason=reason)
        if self._on_open:
            self._on_open(self._service)
