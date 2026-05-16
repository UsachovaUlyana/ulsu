"""Лента: Redis ZSET кэш + Postgres miss-path с фильтрацией по городу."""

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
            SELECT u.id, u.telegram_id, p.city, p.gender, p.age,
                   pr.target_gender, pr.age_min, pr.age_max,
                   p.interests,
                   COALESCE(rv.combined_score, 0) AS combined_score
              FROM users u
              JOIN profiles p ON p.user_id = u.id
         LEFT JOIN preferences pr ON pr.user_id = u.id
         LEFT JOIN ratings rv ON rv.user_id = u.id
             WHERE u.telegram_id = :tid
            """
        ),
        {"tid": telegram_id},
    )
    row = res.mappings().first()
    return dict(row) if row else None


async def _query_candidates(
    session: AsyncSession, viewer: dict, exclude_telegram_id: int | None = None
) -> list[dict[str, Any]]:
    """Returns [{telegram_id, user_id, name, age, city, interests, combined_score}]"""
    target_gender = viewer.get("target_gender")
    age_min = viewer.get("age_min") or 18
    age_max = viewer.get("age_max") or 99

    extra_where = ""
    params = {
        "viewer_id": viewer["id"],
        "age_min": age_min,
        "age_max": age_max,
        "target_gender": target_gender,
    }
    if exclude_telegram_id is not None:
        extra_where = "AND u.telegram_id <> :exclude_tid"
        params["exclude_tid"] = exclude_telegram_id

    sql = f"""
        SELECT u.id              AS user_id,
               u.telegram_id     AS telegram_id,
               p.name, p.age, p.gender, p.city, p.bio, p.interests,
               COALESCE(r.combined_score, 0) AS combined_score,
               COALESCE(r.primary_score, 0) AS primary_score,
               COALESCE(pr.peer_avg, 0) AS peer_avg,
               COALESCE(pr.peer_count, 0) AS peer_count
          FROM users u
          JOIN profiles p ON p.user_id = u.id
     LEFT JOIN ratings  r ON r.user_id = u.id
     LEFT JOIN (
               SELECT reviewee_id AS user_id,
                      AVG(score) AS peer_avg,
                      COUNT(*) AS peer_count
                 FROM peer_reviews
                GROUP BY reviewee_id
              ) pr ON pr.user_id = u.id
         WHERE u.id <> :viewer_id
           AND p.age BETWEEN :age_min AND :age_max
           AND (:target_gender = 'any' OR p.gender = :target_gender OR :target_gender IS NULL)
           AND (
               (SELECT city FROM profiles WHERE user_id = :viewer_id) IS NULL
               OR LOWER(p.city) = LOWER((SELECT city FROM profiles WHERE user_id = :viewer_id))
           )
           AND NOT EXISTS (
               SELECT 1 FROM swipes s
                WHERE s.swiper_id = :viewer_id AND s.target_id = u.id
           )
           {extra_where}
         ORDER BY COALESCE(pr.peer_count, 0) DESC, COALESCE(r.combined_score, 0) DESC
         LIMIT 200
    """
    res = await session.execute(
        text(sql),
        params,
    )
    rows = [dict(r) for r in res.mappings().all()]
    return rows


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
    viewer_score = float(viewer.get("combined_score") or 0.0)
    candidate_score = float(candidate.get("combined_score") or 0.0)
    base = (viewer_score + candidate_score) / 2.0
    overlap = _interest_overlap_boost(
        viewer.get("interests"), candidate.get("interests")
    )
    return base + overlap


def _serialize(c: dict) -> dict:
    peer_count = int(c.get("peer_count") or 0)
    peer_avg = float(c.get("peer_avg") or 0)
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
        "primary_score": float(c.get("primary_score") or 0),
        "peer_rating": {
            "peer_avg": round(peer_avg, 2) if peer_count > 0 else None,
            "peer_count": peer_count,
        },
    }


async def get_next_candidate(
    session: AsyncSession, telegram_id: int, exclude_telegram_id: int | None = None
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
            # If the cached candidate matches exclude_telegram_id, skip it
            if exclude_telegram_id is not None and cached.get("telegram_id") == exclude_telegram_id:
                await redis.zrem(key, member)
                raw = await redis.zpopmax(key, count=1)
                if raw:
                    member, _score = raw[0]
                    cached = json.loads(member)
                else:
                    # Cache empty after exclusion — fall through to miss-path
                    cached = None
            if cached is not None:
                feed_response_seconds.observe(time.perf_counter() - start)
                return cached
        except json.JSONDecodeError:
            logger.warning("feed_cache_corrupt", key=key)

    # Miss: rebuild
    candidates = await _query_candidates(session, viewer, exclude_telegram_id)
    for c in candidates:
        c["personalised"] = _personalised_score(viewer, c)

    candidates.sort(key=lambda c: (c.get("peer_count", 0), c["personalised"]), reverse=True)
    top = candidates[: settings.feed_batch_size]
    if not top:
        feed_response_seconds.observe(time.perf_counter() - start)
        return None

    # Populate the cache and pop the top one
    pipe = redis.pipeline()
    for c in top:
        member = json.dumps(_serialize(c), ensure_ascii=False, default=str)
        score = c.get("peer_count", 0) * 1000 + c["personalised"]
        pipe.zadd(key, {member: score})
    pipe.expire(key, settings.feed_cache_ttl_seconds)
    await pipe.execute()

    # Pop the top scored — same logic as cache-hit path
    raw = await redis.zpopmax(key, count=1)
    feed_response_seconds.observe(time.perf_counter() - start)
    if not raw:
        return None
    member, _ = raw[0]
    return json.loads(member)


