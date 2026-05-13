from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import Match, Swipe

router = APIRouter(prefix="/api/v1")


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


@router.get("/health")
async def health():
    return {"status": "ok"}
