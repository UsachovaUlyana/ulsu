from __future__ import annotations

import asyncio
import time

import pytest

from app.api_client import ApiClient, ApiError, CircuitOpenApiError


class _SlowTimeoutContext:
    async def __aenter__(self):
        await asyncio.sleep(0.2)
        raise asyncio.TimeoutError()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    closed = False

    def request(self, *args, **kwargs):
        return _SlowTimeoutContext()


def test_circuit_short_circuit_is_fast_after_timeout_failure() -> None:
    async def scenario() -> None:
        client = ApiClient(
            profile_service_url="http://profile-service:8001",
            ranking_service_url="http://ranking-service:8002",
            matching_service_url="http://matching-service:8003",
            request_timeout_seconds=0.2,
            failure_threshold=1,
            open_timeout_seconds=30,
            half_open_max_calls=1,
        )
        client._session = _FakeSession()
        try:
            t1 = time.perf_counter()
            with pytest.raises(ApiError):
                await client.get_feed(100)
            first_elapsed = time.perf_counter() - t1

            t2 = time.perf_counter()
            with pytest.raises(CircuitOpenApiError):
                await client.get_feed(100)
            second_elapsed = time.perf_counter() - t2
        finally:
            client._session = None

        assert first_elapsed >= 0.15
        assert second_elapsed < 0.1
        assert second_elapsed * 4 < first_elapsed

    asyncio.run(scenario())
