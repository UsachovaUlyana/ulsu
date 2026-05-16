"""Async HTTP client for the internal microservices (profile, ranking, matching)."""

from __future__ import annotations

from typing import Any

import aiohttp

from shared.logging import get_logger

from .config import settings

logger = get_logger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"api error {status}: {body}")
        self.status = status
        self.body = body


class ApiClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: aiohttp.FormData | None = None,
    ) -> dict[str, Any] | None:
        session = await self.session()
        async with session.request(method, url, json=json, data=data) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.warning(
                    "api_error", method=method, url=url, status=resp.status, body=text
                )
                raise ApiError(resp.status, text)
            if resp.status == 204 or not text:
                return None
            return await resp.json(content_type=None)

    # ---- Profile service ----

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
        referral_code_used: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{settings.profile_service_url}/api/v1/users/",
            json={
                "telegram_id": telegram_id,
                "username": username,
                "referral_code_used": referral_code_used,
            },
        )

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET", f"{settings.profile_service_url}/api/v1/users/{telegram_id}"
            )
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def upsert_profile(
        self, telegram_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"{settings.profile_service_url}/api/v1/users/{telegram_id}/profile",
            json=payload,
        )

    async def upsert_preferences(
        self, telegram_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"{settings.profile_service_url}/api/v1/users/{telegram_id}/preferences",
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
            "POST",
            f"{settings.profile_service_url}/api/v1/users/{telegram_id}/photos",
            data=form,
        )

    async def apply_referral(
        self, inviter_code: str, invitee_telegram_id: int
    ) -> dict[str, Any] | None:
        try:
            return await self._request(
                "POST",
                f"{settings.profile_service_url}/api/v1/referrals/apply",
                json={
                    "inviter_code": inviter_code,
                    "invitee_telegram_id": invitee_telegram_id,
                },
            )
        except ApiError as e:
            if e.status in (400, 404, 409):
                return None
            raise

    # ---- Ranking service (used in Этап 3) ----

    async def get_feed(
        self, telegram_id: int, exclude_telegram_id: int | None = None
    ) -> dict[str, Any] | None:
        url = f"{settings.ranking_service_url}/api/v1/feed/{telegram_id}"
        if exclude_telegram_id is not None:
            url = f"{url}?exclude_telegram_id={exclude_telegram_id}"
        try:
            return await self._request("GET", url)
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def delete_user(self, telegram_id: int) -> None:
        await self._request(
            "DELETE", f"{settings.profile_service_url}/api/v1/users/{telegram_id}"
        )

    async def get_likes(self, telegram_id: int) -> list[dict]:
        try:
            resp = await self._request(
                "GET",
                f"{settings.matching_service_url}/api/v1/likes/{telegram_id}",
            )
            return resp.get("likes") or []
        except ApiError as e:
            if e.status == 404:
                return []
            raise

    async def get_ratings(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET",
                f"{settings.ranking_service_url}/api/v1/ratings/{telegram_id}",
            )
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def get_matches(self, telegram_id: int) -> list[dict]:
        try:
            resp = await self._request(
                "GET",
                f"{settings.matching_service_url}/api/v1/matches/{telegram_id}",
            )
            return resp.get("matches") or []
        except ApiError as e:
            if e.status == 404:
                return []
            raise

    async def submit_review(
        self, reviewer_telegram_id: int, reviewee_telegram_id: int, score: int
    ) -> dict[str, Any] | None:
        try:
            return await self._request(
                "POST",
                f"{settings.matching_service_url}/api/v1/reviews",
                json={
                    "reviewer_telegram_id": reviewer_telegram_id,
                    "reviewee_telegram_id": reviewee_telegram_id,
                    "score": score,
                },
            )
        except ApiError:
            raise

    async def get_peer_summary(self, telegram_id: int) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET",
                f"{settings.matching_service_url}/api/v1/reviews/{telegram_id}/summary",
            )
        except ApiError as e:
            if e.status == 404:
                return None
            raise


api_client = ApiClient()
