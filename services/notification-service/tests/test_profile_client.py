from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.profile_client import _breaker, get_user
from shared.circuit_breaker import CircuitState


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
async def test_get_user_success():
    resp = _FakeResponse(200, {"telegram_id": 123, "username": "test"})
    with patch("aiohttp.ClientSession", return_value=_FakeSession(response=resp)):
        result = await get_user(123)
    assert result == {"telegram_id": 123, "username": "test"}


@pytest.mark.asyncio
async def test_get_user_not_found():
    resp = _FakeResponse(404)
    with patch("aiohttp.ClientSession", return_value=_FakeSession(response=resp)):
        result = await get_user(123)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_http_500_records_failure():
    resp = _FakeResponse(503)
    with patch("aiohttp.ClientSession", return_value=_FakeSession(response=resp)):
        result = await get_user(123)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_timeout_records_failure():
    with patch(
        "aiohttp.ClientSession",
        return_value=_FakeSession(exc=asyncio.TimeoutError()),
    ):
        result = await get_user(123)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_short_circuits_when_open():
    _breaker._state = CircuitState.OPEN
    _breaker._opened_at = _breaker._time_fn()

    with patch("aiohttp.ClientSession") as mock_session:
        result = await get_user(123)
        mock_session.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    original_threshold = _breaker._failure_threshold
    _breaker._failure_threshold = 2

    try:
        resp = _FakeResponse(503)
        for _ in range(2):
            with patch(
                "aiohttp.ClientSession", return_value=_FakeSession(response=resp)
            ):
                await get_user(123)

        assert _breaker.state == CircuitState.OPEN

        with patch("aiohttp.ClientSession") as mock_session:
            result = await get_user(123)
            mock_session.assert_not_called()
        assert result is None
    finally:
        _breaker._failure_threshold = original_threshold
