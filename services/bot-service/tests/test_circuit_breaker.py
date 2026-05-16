from __future__ import annotations

import asyncio

import pytest

from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


def test_circuit_opens_after_threshold() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            service="ranking",
            failure_threshold=3,
            open_timeout_seconds=10,
            half_open_max_calls=1,
            time_fn=clock.now,
        )

        for _ in range(3):
            execution = await breaker.before_call()
            await breaker.record_failure(execution, reason="timeout")

        assert breaker.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.before_call()

    asyncio.run(scenario())


def test_half_open_success_closes_circuit() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            service="profile",
            failure_threshold=1,
            open_timeout_seconds=5,
            half_open_max_calls=1,
            time_fn=clock.now,
        )

        first = await breaker.before_call()
        await breaker.record_failure(first, reason="http_503")
        assert breaker.state == CircuitState.OPEN

        clock.tick(6)
        probe = await breaker.before_call()
        assert breaker.state == CircuitState.HALF_OPEN
        assert probe.is_probe is True

        await breaker.record_success(probe)
        assert breaker.state == CircuitState.CLOSED

    asyncio.run(scenario())


def test_half_open_failure_reopens_circuit() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            service="matching",
            failure_threshold=1,
            open_timeout_seconds=5,
            half_open_max_calls=1,
            time_fn=clock.now,
        )

        first = await breaker.before_call()
        await breaker.record_failure(first, reason="timeout")
        assert breaker.state == CircuitState.OPEN

        clock.tick(6)
        probe = await breaker.before_call()
        await breaker.record_failure(probe, reason="timeout")
        assert breaker.state == CircuitState.OPEN

    asyncio.run(scenario())


def test_half_open_limited_probe_calls() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            service="ranking",
            failure_threshold=1,
            open_timeout_seconds=5,
            half_open_max_calls=1,
            time_fn=clock.now,
        )

        first = await breaker.before_call()
        await breaker.record_failure(first, reason="timeout")
        clock.tick(6)

        probe = await breaker.before_call()
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.before_call()
        await breaker.record_success(probe)
        assert breaker.state == CircuitState.CLOSED

    asyncio.run(scenario())
