from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_async_session
from .feed_service import get_next_candidate
from .photos_client import get_photos

router = APIRouter(prefix="/api/v1")


@router.get("/feed/{telegram_id}")
async def feed(
    telegram_id: int,
    exclude_telegram_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    candidate = await get_next_candidate(session, telegram_id, exclude_telegram_id)
    if candidate is None:
        return {"profile": None}
    candidate["photos"] = await get_photos(candidate["telegram_id"])
    return candidate


@router.get("/ratings/{telegram_id}")
async def ratings(
    telegram_id: int, session: AsyncSession = Depends(get_async_session)
):
    res = await session.execute(
        text(
            """
            SELECT r.primary_score, r.behavioral_score, r.referral_bonus,
                   r.peer_score, r.combined_score, r.updated_at
              FROM users u
         LEFT JOIN ratings r ON r.user_id = u.id
             WHERE u.telegram_id = :tid
            """
        ),
        {"tid": telegram_id},
    )
    row = res.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return dict(row)


@router.get("/health")
async def health():
    return {"status": "ok"}
