"""Async HTTP client for internal microservices with circuit breakers."""

from __future__ import annotations

import asyncio
from typing import Any

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


class ApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"api error {status}: {body}")
        self.status = status
        self.body = body


class CircuitOpenApiError(ApiError):
    def __init__(self, service: str) -> None:
        super().__init__(
            503, f"Сервис {service} временно недоступен. Попробуй позже."
        )
        self.service = service


class ApiClient:
    def __init__(
        self,
        *,
        profile_service_url: str | None = None,
        ranking_service_url: str | None = None,
        matching_service_url: str | None = None,
        request_timeout_seconds: float | None = None,
        failure_threshold: int | None = None,
        open_timeout_seconds: float | None = None,
        half_open_max_calls: int | None = None,
    ) -> None:
        self._session: aiohttp.ClientSession | None = None

        self._profile_service_url = profile_service_url or settings.profile_service_url
        self._ranking_service_url = ranking_service_url or settings.ranking_service_url
        self._matching_service_url = matching_service_url or settings.matching_service_url
        self._request_timeout_seconds = request_timeout_seconds or settings.api_timeout_seconds
        self._failure_threshold = failure_threshold or settings.circuit_failure_threshold
        self._open_timeout_seconds = (
            open_timeout_seconds or settings.circuit_open_timeout_seconds
        )
        self._half_open_max_calls = (
            half_open_max_calls or settings.circuit_half_open_max_calls
        )

        self._breakers = {
            "profile": self._make_breaker("profile"),
            "ranking": self._make_breaker("ranking"),
            "matching": self._make_breaker("matching"),
        }

    def _make_breaker(self, service: str) -> CircuitBreaker:
        return CircuitBreaker(
            service=service,
            failure_threshold=self._failure_threshold,
            open_timeout_seconds=self._open_timeout_seconds,
            half_open_max_calls=self._half_open_max_calls,
            on_open=lambda svc: circuit_open_total.labels(service=svc).inc(),
            on_short_circuit=lambda svc: circuit_short_circuit_total.labels(
                service=svc
            ).inc(),
            on_half_open=lambda svc: circuit_half_open_total.labels(service=svc).inc(),
        )

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._request_timeout_seconds)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        service: str,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: aiohttp.FormData | None = None,
    ) -> dict[str, Any] | None:
        breaker = self._breakers[service]
        try:
            execution = await breaker.before_call()
        except CircuitBreakerOpenError as e:
            raise CircuitOpenApiError(e.service) from e

        session = await self.session()
        try:
            async with session.request(method, url, json=json, data=data) as resp:
                text = await resp.text()
                if resp.status >= 500:
                    await breaker.record_failure(execution, reason=f"http_{resp.status}")
                else:
                    await breaker.record_success(execution)

                if resp.status >= 400:
                    logger.warning(
                        "api_error",
                        service=service,
                        method=method,
                        url=url,
                        status=resp.status,
                        body=text,
                    )
                    raise ApiError(resp.status, text)

                if resp.status == 204 or not text:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            await breaker.record_failure(execution, reason=e.__class__.__name__)
            logger.warning(
                "api_transport_error",
                service=service,
                method=method,
                url=url,
                error=e.__class__.__name__,
            )
            raise ApiError(503, str(e)) from e

    # ---- Profile service ----

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
        referral_code_used: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "profile",
            "POST",
            f"{self._profile_service_url}/api/v1/users/",
            json={
                "telegram_id": telegram_id,
                "username": username,
                "referral_code_used": referral_code_used,
            },
        )

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "profile", "GET", f"{self._profile_service_url}/api/v1/users/{telegram_id}"
            )
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def upsert_profile(
        self, telegram_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "profile",
            "PUT",
            f"{self._profile_service_url}/api/v1/users/{telegram_id}/profile",
            json=payload,
        )

    async def upsert_preferences(
        self, telegram_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "profile",
            "PUT",
            f"{self._profile_service_url}/api/v1/users/{telegram_id}/preferences",
            json=payload,
        )

    async def upload_photo(
        self, telegram_id: int, file_bytes: bytes, filename: str = "photo.jpg"
    ) -> dict[str, Any]:
        form = aiohttp.FormData()
        form.add_field(
            "file", file_bytes, filename=filename, content_type="image/jpeg"
        )
        return await self._request(
            "profile",
            "POST",
            f"{self._profile_service_url}/api/v1/users/{telegram_id}/photos",
            data=form,
        )

    async def apply_referral(
        self, inviter_code: str, invitee_telegram_id: int
    ) -> dict[str, Any] | None:
        try:
            return await self._request(
                "profile",
                "POST",
                f"{self._profile_service_url}/api/v1/referrals/apply",
                json={
                    "inviter_code": inviter_code,
                    "invitee_telegram_id": invitee_telegram_id,
                },
            )
        except ApiError as e:
            if e.status in (400, 404, 409):
                return None
            raise

    # ---- Ranking service ----

    async def get_feed(
        self, telegram_id: int, exclude_telegram_id: int | None = None
    ) -> dict[str, Any] | None:
        url = f"{self._ranking_service_url}/api/v1/feed/{telegram_id}"
        if exclude_telegram_id is not None:
            url = f"{url}?exclude_telegram_id={exclude_telegram_id}"
        try:
            return await self._request("ranking", "GET", url)
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def get_ratings(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "ranking",
                "GET",
                f"{self._ranking_service_url}/api/v1/ratings/{telegram_id}",
            )
        except CircuitOpenApiError:
            return None
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def delete_user(self, telegram_id: int) -> None:
        await self._request(
            "profile", "DELETE", f"{self._profile_service_url}/api/v1/users/{telegram_id}"
        )

    # ---- Matching service ----

    async def get_likes(self, telegram_id: int) -> list[dict[str, Any]]:
        try:
            resp = await self._request(
                "matching",
                "GET",
                f"{self._matching_service_url}/api/v1/likes/{telegram_id}",
            )
            return (resp or {}).get("likes") or []
        except CircuitOpenApiError:
            return []
        except ApiError as e:
            if e.status == 404:
                return []
            raise

    async def get_matches(self, telegram_id: int) -> list[dict[str, Any]]:
        try:
            resp = await self._request(
                "matching",
                "GET",
                f"{self._matching_service_url}/api/v1/matches/{telegram_id}",
            )
            return (resp or {}).get("matches") or []
        except CircuitOpenApiError:
            return []
        except ApiError as e:
            if e.status == 404:
                return []
            raise

    async def submit_review(
        self, reviewer_telegram_id: int, reviewee_telegram_id: int, score: float
    ) -> dict[str, Any] | None:
        return await self._request(
            "matching",
            "POST",
            f"{self._matching_service_url}/api/v1/reviews",
            json={
                "reviewer_telegram_id": reviewer_telegram_id,
                "reviewee_telegram_id": reviewee_telegram_id,
                "score": score,
            },
        )

    async def get_peer_summary(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "matching",
                "GET",
                f"{self._matching_service_url}/api/v1/reviews/{telegram_id}/summary",
            )
        except CircuitOpenApiError:
            return None
        except ApiError as e:
            if e.status == 404:
                return None
            raise


api_client = ApiClient()
