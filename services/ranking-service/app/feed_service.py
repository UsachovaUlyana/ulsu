"""Лента: Redis ZSET кэш + Postgres miss-path с Haversine."""

from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.metrics import feed_response_seconds

from .config import settings
from .formulas import haversine_km

logger = get_logger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _cache_key(user_id: int) -> str:
    return f"feed:{user_id}"


async def _resolve_user(session: AsyncSession, telegram_id: int) -> dict | None:
    res = await session.execute(
        text(
            """
            SELECT u.id, u.telegram_id, p.lat, p.lon, p.gender, p.age,
                   pr.target_gender, pr.age_min, pr.age_max, pr.max_distance_km,
                   p.interests
              FROM users u
              JOIN profiles p ON p.user_id = u.id
         LEFT JOIN preferences pr ON pr.user_id = u.id
             WHERE u.telegram_id = :tid
            """
        ),
        {"tid": telegram_id},
    )
    row = res.mappings().first()
    return dict(row) if row else None


async def _query_candidates(
    session: AsyncSession, viewer: dict
) -> list[dict[str, Any]]:
    """Returns [{telegram_id, user_id, name, age, lat, lon, interests, combined_score}]"""
    target_gender = viewer.get("target_gender")
    age_min = viewer.get("age_min") or 18
    age_max = viewer.get("age_max") or 99

    sql = """
        SELECT u.id              AS user_id,
               u.telegram_id     AS telegram_id,
               p.name, p.age, p.gender, p.city, p.bio, p.interests,
               p.lat, p.lon,
               COALESCE(r.combined_score, 0) AS combined_score
          FROM users u
          JOIN profiles p ON p.user_id = u.id
     LEFT JOIN ratings  r ON r.user_id = u.id
         WHERE u.id <> :viewer_id
           AND p.age BETWEEN :age_min AND :age_max
           AND (:target_gender = 'any' OR p.gender = :target_gender OR :target_gender IS NULL)
           AND NOT EXISTS (
               SELECT 1 FROM swipes s
                WHERE s.swiper_id = :viewer_id AND s.target_id = u.id
           )
         LIMIT 200
    """
    res = await session.execute(
        text(sql),
        {
            "viewer_id": viewer["id"],
            "age_min": age_min,
            "age_max": age_max,
            "target_gender": target_gender,
        },
    )
    rows = [dict(r) for r in res.mappings().all()]
    return rows


def _filter_by_distance(
    candidates: list[dict], viewer: dict
) -> list[dict]:
    """Annotate distance, drop those beyond max_distance_km. Viewers without
    geolocation see everyone (no distance shown)."""
    max_km = viewer.get("max_distance_km")
    vlat, vlon = viewer.get("lat"), viewer.get("lon")
    out = []
    for c in candidates:
        if vlat is not None and vlon is not None and c["lat"] is not None and c["lon"] is not None:
            d = haversine_km(vlat, vlon, c["lat"], c["lon"])
            if max_km is not None and d > max_km:
                continue
            c["distance_km"] = round(d, 2)
        else:
            c["distance_km"] = None
        out.append(c)
    return out


def _interest_overlap_boost(viewer_interests, candidate_interests) -> float:
    if not viewer_interests or not candidate_interests:
        return 0.0
    a = {x.lower() for x in viewer_interests}
    b = {x.lower() for x in candidate_interests}
    overlap = len(a & b)
    if not overlap:
        return 0.0
    return min(0.15, overlap * 0.05)


def _personalised_score(viewer: dict, candidate: dict) -> float:
    base = float(candidate.get("combined_score") or 0.0)
    overlap = _interest_overlap_boost(
        viewer.get("interests"), candidate.get("interests")
    )
    # Bias against far-away matches even within the radius
    dist = candidate.get("distance_km")
    distance_penalty = 0.0
    if dist is not None:
        # 0 km → 0 penalty; 100 km → 0.05 penalty
        distance_penalty = min(0.05, dist / 2000)
    return base + overlap - distance_penalty


def _serialize(c: dict) -> dict:
    return {
        "user_id": c["user_id"],
        "telegram_id": c["telegram_id"],
        "profile": {
            "name": c["name"],
            "age": c["age"],
            "gender": c["gender"],
            "city": c.get("city"),
            "bio": c.get("bio"),
            "interests": c.get("interests"),
        },
        "compatibility": round(min(1.0, max(0.0, c["personalised"])), 4),
        "distance_km": c.get("distance_km"),
    }


async def get_next_candidate(
    session: AsyncSession, telegram_id: int
) -> dict | None:
    start = time.perf_counter()
    viewer = await _resolve_user(session, telegram_id)
    if viewer is None:
        return None

    redis = get_redis()
    key = _cache_key(viewer["id"])

    # Cache hit?
    raw = await redis.zpopmax(key, count=1)
    if raw:
        member, _score = raw[0]
        try:
            cached = json.loads(member)
            feed_response_seconds.observe(time.perf_counter() - start)
            return cached
        except json.JSONDecodeError:
            logger.warning("feed_cache_corrupt", key=key)

    # Miss: rebuild
    candidates = await _query_candidates(session, viewer)
    candidates = _filter_by_distance(candidates, viewer)

    for c in candidates:
        c["personalised"] = _personalised_score(viewer, c)

    candidates.sort(key=lambda c: c["personalised"], reverse=True)
    top = candidates[: settings.feed_batch_size]
    if not top:
        feed_response_seconds.observe(time.perf_counter() - start)
        return None

    # Populate the cache and pop the top one
    pipe = redis.pipeline()
    for c in top:
        member = json.dumps(_serialize(c), ensure_ascii=False, default=str)
        pipe.zadd(key, {member: c["personalised"]})
    pipe.expire(key, settings.feed_cache_ttl_seconds)
    await pipe.execute()

    # Pop the top scored — same logic as cache-hit path
    raw = await redis.zpopmax(key, count=1)
    feed_response_seconds.observe(time.perf_counter() - start)
    if not raw:
        return None
    member, _ = raw[0]
    return json.loads(member)


