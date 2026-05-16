from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.photos_client import _breaker, get_photos
from shared.circuit_breaker import CircuitBreakerOpenError, CircuitState


@pytest.fixture(autouse=True)
def reset_breaker():
    """Ensure fresh circuit breaker state for every test."""
    _breaker._state = CircuitState.CLOSED
    _breaker._consecutive_failures = 0
    _breaker._opened_at = 0.0
    _breaker._half_open_in_flight = 0
    yield
    _breaker._state = CircuitState.CLOSED
    _breaker._consecutive_failures = 0
    _breaker._opened_at = 0.0
    _breaker._half_open_in_flight = 0


class _FakeResponse:
    def __init__(self, status: int, json_data: dict | None = None):
        self.status = status
        self._json = json_data

    async def json(self):
        return self._json or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_get_photos_success():
    resp = _FakeResponse(200, {"photos": [{"url": "http://example.com/1.jpg"}]})
    with patch("aiohttp.ClientSession", return_value=_FakeSession(response=resp)):
        result = await get_photos(123)
    assert result == [{"url": "http://example.com/1.jpg"}]


@pytest.mark.asyncio
async def test_get_photos_http_500_records_failure():
    resp = _FakeResponse(503)
    with patch("aiohttp.ClientSession", return_value=_FakeSession(response=resp)):
        result = await get_photos(123)
    assert result == []


@pytest.mark.asyncio
async def test_get_photos_timeout_records_failure():
    with patch(
        "aiohttp.ClientSession",
        return_value=_FakeSession(exc=asyncio.TimeoutError()),
    ):
        result = await get_photos(123)
    assert result == []


@pytest.mark.asyncio
async def test_get_photos_short_circuits_when_open():
    # Force circuit open
    _breaker._state = CircuitState.OPEN
    _breaker._opened_at = _breaker._time_fn()

    # Should return empty list instantly without making HTTP call
    with patch("aiohttp.ClientSession") as mock_session:
        result = await get_photos(123)
        mock_session.assert_not_called()
    assert result == []


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    # Temporarily lower threshold for faster test
    original_threshold = _breaker._failure_threshold
    _breaker._failure_threshold = 2

    try:
        resp = _FakeResponse(503)
        for _ in range(2):
            with patch(
                "aiohttp.ClientSession", return_value=_FakeSession(response=resp)
            ):
                await get_photos(123)

        assert _breaker.state == CircuitState.OPEN

        # Next call must short-circuit
        with patch("aiohttp.ClientSession") as mock_session:
            result = await get_photos(123)
            mock_session.assert_not_called()
        assert result == []
    finally:
        _breaker._failure_threshold = original_threshold
