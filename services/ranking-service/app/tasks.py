"""Celery-задачи пересчёта рейтингов.

L1 (primary) считается реактивно — на событие profile_events.
L2 (behavioral) пересчитывается раз в 15 минут по агрегатам.
L3 (combined) — раз в час и сразу инвалидирует кэш ленты.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import text

from shared.logging import get_logger
from shared.metrics import recalc_duration_seconds

from .celery_app import celery_app
from .config import settings
from .database import SyncSessionLocal
from .formulas import behavioral_score, combined_score, primary_score

logger = get_logger(__name__)


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _invalidate_feed_cache() -> None:
    r = _redis_client()
    keys = list(r.scan_iter(match="feed:*", count=500))
    if keys:
        r.delete(*keys)
        logger.info("feed_cache_invalidated", count=len(keys))


# ---------------- L1 ----------------


def _compute_primary_for_user(session, user_id: int) -> float:
    row = session.execute(
        text(
            """
            SELECT p.name, p.age, p.gender, p.city, p.bio, p.interests,
                   (SELECT count(*) FROM photos WHERE user_id = :uid) AS photos_count,
                   (SELECT 1 FROM preferences WHERE user_id = :uid) AS has_prefs
              FROM profiles p
             WHERE p.user_id = :uid
            """
        ),
        {"uid": user_id},
    ).mappings().first()
    if row is None:
        return 0.0
    return primary_score(
        has_name=bool(row["name"]),
        has_age=bool(row["age"]),
        has_gender=bool(row["gender"]),
        has_city=bool(row["city"]),
        has_bio=bool(row["bio"]),
        interests_count=len(row["interests"] or []),
        photos_count=int(row["photos_count"] or 0),
        has_preferences=bool(row["has_prefs"]),
    )


def _upsert_rating(session, user_id: int, **fields) -> None:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(f":{k}" for k in fields.keys())
    set_clause = ", ".join(f"{k} = EXCLUDED.{k}" for k in fields.keys())
    session.execute(
        text(
            f"""
            INSERT INTO ratings (user_id, {cols})
            VALUES (:user_id, {placeholders})
            ON CONFLICT (user_id) DO UPDATE
               SET {set_clause}, updated_at = NOW()
            """
        ),
        {"user_id": user_id, **fields},
    )


@celery_app.task(name="app.tasks.recalc_primary_for_user")
def recalc_primary_for_user(user_id: int) -> None:
    start = time.perf_counter()
    with SyncSessionLocal() as session:
        score = _compute_primary_for_user(session, user_id)
        _upsert_rating(session, user_id, primary_score=score)
        session.commit()
    recalc_duration_seconds.labels(level="primary").observe(time.perf_counter() - start)
    logger.info("primary_recalculated", user_id=user_id, score=score)


# ---------------- L2 ----------------


@celery_app.task(name="app.tasks.recalc_behavioral_all")
def recalc_behavioral_all() -> None:
    start = time.perf_counter()
    window_start = datetime.now(timezone.utc) - timedelta(days=14)

    with SyncSessionLocal() as session:
        users = session.execute(text("SELECT id FROM users")).scalars().all()
        for user_id in users:
            stats = session.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM swipes WHERE target_id = :uid AND action = 'like'
                          AND created_at >= :since) AS likes,
                      (SELECT count(*) FROM swipes WHERE target_id = :uid AND action = 'skip'
                          AND created_at >= :since) AS skips,
                      (SELECT count(*) FROM matches WHERE (user1_id = :uid OR user2_id = :uid)
                          AND created_at >= :since) AS mutual,
                      (SELECT count(*) FROM matches WHERE (user1_id = :uid OR user2_id = :uid)
                          AND started_dialog_at IS NOT NULL
                          AND started_dialog_at >= :since) AS dialogs,
                      (SELECT count(DISTINCT hour_of_day) FROM activity_log
                         WHERE user_id = :uid AND created_at >= :since) AS active_hours
                    """
                ),
                {"uid": user_id, "since": window_start},
            ).mappings().first()
            score = behavioral_score(
                likes_received=stats["likes"],
                skips_received=stats["skips"],
                mutual_matches=stats["mutual"],
                dialogs_started=stats["dialogs"],
                active_hours_count=stats["active_hours"],
            )
            _upsert_rating(session, user_id, behavioral_score=score)
        session.commit()
    recalc_duration_seconds.labels(level="behavioral").observe(time.perf_counter() - start)
    logger.info("behavioral_recalculated", users=len(users))


# ---------------- L3 ----------------


@celery_app.task(name="app.tasks.recalc_combined_all")
def recalc_combined_all() -> None:
    start = time.perf_counter()
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT u.id AS user_id,
                       COALESCE(r.primary_score, 0)    AS p,
                       COALESCE(r.behavioral_score, 0) AS b,
                       COALESCE(SUM(rf.bonus_value), 0) AS ref_bonus
                  FROM users u
             LEFT JOIN ratings r  ON r.user_id  = u.id
             LEFT JOIN referrals rf ON rf.inviter_id = u.id OR rf.invitee_id = u.id
                 GROUP BY u.id, r.primary_score, r.behavioral_score
                """
            )
        ).mappings().all()
        for row in rows:
            score = combined_score(row["p"], row["b"], row["ref_bonus"])
            _upsert_rating(
                session,
                row["user_id"],
                referral_bonus=min(row["ref_bonus"], settings.referral_bonus_cap),
                combined_score=score,
            )
        session.commit()
    _invalidate_feed_cache()
    recalc_duration_seconds.labels(level="combined").observe(time.perf_counter() - start)
    logger.info("combined_recalculated", users=len(rows))
