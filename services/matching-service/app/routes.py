from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.events import EXCHANGE_REVIEWS, RK_REVIEW_CREATED, RK_REVIEW_UPDATED
from shared.logging import get_logger

from .consumer import publisher
from .database import get_session
from .models import Match, PeerReview, Swipe

router = APIRouter(prefix="/api/v1")
logger = get_logger(__name__)


class ReviewPayload(BaseModel):
    reviewer_telegram_id: int
    reviewee_telegram_id: int
    score: float = Field(..., ge=1.0, le=5.0)

    @field_validator("score")
    @classmethod
    def validate_step(cls, value: float) -> float:
        scaled = round(value * 10)
        if abs(value * 10 - scaled) > 1e-9:
            raise ValueError("score must use 0.1 step")
        return scaled / 10


@router.get("/matches/{telegram_id}")
async def list_matches(telegram_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"), {"tid": telegram_id}
    )
    row = res.first()
    if row is None:
        return {"matches": []}
    user_id = row[0]
    matches = (
        await session.execute(
            select(Match).where(or_(Match.user1_id == user_id, Match.user2_id == user_id))
        )
    ).scalars().all()
    out = []
    for m in matches:
        partner_id = m.user2_id if m.user1_id == user_id else m.user1_id
        partner = (
            await session.execute(
                text("SELECT telegram_id FROM users WHERE id = :uid"),
                {"uid": partner_id},
            )
        ).first()
        out.append(
            {
                "match_id": m.id,
                "partner_user_id": partner_id,
                "partner_telegram_id": partner[0] if partner else None,
                "created_at": m.created_at.isoformat(),
            }
        )
    return {"matches": out}


@router.get("/swipes/{telegram_id}/history")
async def swipe_history(
    telegram_id: int, session: AsyncSession = Depends(get_session)
):
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"), {"tid": telegram_id}
    )
    row = res.first()
    if row is None:
        return {"swipes": []}
    user_id = row[0]
    rows = (
        await session.execute(
            select(Swipe.target_id, Swipe.action, Swipe.created_at).where(
                Swipe.swiper_id == user_id
            )
        )
    ).all()
    return {
        "swipes": [
            {"target_id": t, "action": a, "created_at": c.isoformat()}
            for t, a, c in rows
        ]
    }


@router.get("/likes/{telegram_id}")
async def list_likes(
    telegram_id: int, session: AsyncSession = Depends(get_session)
):
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"), {"tid": telegram_id}
    )
    row = res.first()
    if row is None:
        return {"likes": []}
    user_id = row[0]
    rows = await session.execute(
        text(
            """
            SELECT u.telegram_id,
                   COALESCE(r.combined_score, 0) AS combined_score,
                   COALESCE(r.primary_score, 0) AS primary_score,
                   COALESCE(pr.peer_avg, 0) AS peer_avg,
                   COALESCE(pr.peer_count, 0) AS peer_count
              FROM swipes s
              JOIN users u ON u.id = s.swiper_id
         LEFT JOIN ratings r ON r.user_id = u.id
         LEFT JOIN (
               SELECT reviewee_id AS user_id,
                      AVG(score) AS peer_avg,
                      COUNT(*) AS peer_count
                 FROM peer_reviews
                GROUP BY reviewee_id
              ) pr ON pr.user_id = u.id
             WHERE s.target_id = :user_id
               AND s.action = 'like'
               AND NOT EXISTS (
                   SELECT 1 FROM swipes s2
                    WHERE s2.swiper_id = :user_id AND s2.target_id = s.swiper_id
               )
             ORDER BY s.created_at DESC
             LIMIT 50
            """
        ),
        {"user_id": user_id},
    )
    likes = [
        {
            "telegram_id": r[0],
            "combined_score": r[1],
            "primary_score": r[2],
            "peer_avg": float(r[3]) if r[4] and r[4] > 0 else None,
            "peer_count": int(r[4] or 0),
        }
        for r in rows.all()
    ]
    return {"likes": likes}


@router.post("/reviews")
async def create_or_update_review(
    payload: ReviewPayload, session: AsyncSession = Depends(get_session)
):
    # Resolve telegram IDs to internal IDs
    res = await session.execute(
        text(
            "SELECT id FROM users WHERE telegram_id = :tid"
        ),
        {"tid": payload.reviewer_telegram_id},
    )
    reviewer_row = res.first()
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"),
        {"tid": payload.reviewee_telegram_id},
    )
    reviewee_row = res.first()

    if reviewer_row is None or reviewee_row is None:
        raise HTTPException(status_code=404, detail="user not found")

    reviewer_id = reviewer_row[0]
    reviewee_id = reviewee_row[0]

    if reviewer_id == reviewee_id:
        raise HTTPException(status_code=400, detail="cannot review yourself")

    # Verify match exists
    u1, u2 = sorted((reviewer_id, reviewee_id))
    match = (
        await session.execute(
            select(Match).where(Match.user1_id == u1, Match.user2_id == u2)
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(
            status_code=403, detail="can only review users you have matched with"
        )

    # Upsert review
    stmt = (
        pg_insert(PeerReview)
        .values(
            reviewer_id=reviewer_id,
            reviewee_id=reviewee_id,
            score=payload.score,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            index_elements=["reviewer_id", "reviewee_id"],
            set_={"score": payload.score, "updated_at": datetime.now(timezone.utc)},
        )
    )
    await session.execute(stmt)
    await session.commit()

    # Fetch the review row to get id
    review = (
        await session.execute(
            select(PeerReview).where(
                PeerReview.reviewer_id == reviewer_id,
                PeerReview.reviewee_id == reviewee_id,
            )
        )
    ).scalar_one()

    # Publish event
    routing_key = RK_REVIEW_CREATED if review.created_at == review.updated_at else RK_REVIEW_UPDATED
    await publisher.publish(
        EXCHANGE_REVIEWS,
        routing_key,
        {
            "reviewer_id": reviewer_id,
            "reviewee_id": reviewee_id,
            "reviewer_telegram_id": payload.reviewer_telegram_id,
            "reviewee_telegram_id": payload.reviewee_telegram_id,
            "score": payload.score,
            "created_at": review.created_at.isoformat(),
        },
    )

    return {
        "review_id": review.id,
        "reviewer_id": reviewer_id,
        "reviewee_id": reviewee_id,
        "score": payload.score,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/reviews/{telegram_id}/summary")
async def review_summary(
    telegram_id: int, session: AsyncSession = Depends(get_session)
):
    res = await session.execute(
        text("SELECT id FROM users WHERE telegram_id = :tid"), {"tid": telegram_id}
    )
    row = res.first()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    user_id = row[0]

    stats = await session.execute(
        text(
            """
            SELECT COALESCE(AVG(score), 0) AS peer_avg,
                   COUNT(*) AS peer_count
              FROM peer_reviews
             WHERE reviewee_id = :uid
            """
        ),
        {"uid": user_id},
    )
    stats_row = stats.mappings().first()
    peer_avg = float(stats_row["peer_avg"]) if stats_row["peer_avg"] else None
    peer_count = int(stats_row["peer_count"])

    return {
        "peer_avg": peer_avg,
        "peer_count": peer_count,
    }


@router.get("/health")
async def health():
    return {"status": "ok"}
