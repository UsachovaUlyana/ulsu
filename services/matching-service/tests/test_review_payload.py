from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routes import ReviewPayload


def test_review_payload_accepts_tenths_step():
    payload = ReviewPayload(
        reviewer_telegram_id=1,
        reviewee_telegram_id=2,
        score=4.5,
    )
    assert payload.score == pytest.approx(4.5, abs=1e-9)


@pytest.mark.parametrize("score", [4.55, 5.1, 0.9])
def test_review_payload_rejects_invalid_score(score: float):
    with pytest.raises(ValidationError):
        ReviewPayload(
            reviewer_telegram_id=1,
            reviewee_telegram_id=2,
            score=score,
        )
