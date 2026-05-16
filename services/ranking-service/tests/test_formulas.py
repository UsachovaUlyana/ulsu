from __future__ import annotations

import pytest

from app.config import settings
from app.formulas import (
    behavioral_score,
    combined_after_review,
    combined_score,
    peer_score_formula,
    primary_score,
)


def test_primary_score_empty():
    s = primary_score(
        has_name=False,
        has_age=False,
        has_gender=False,
        has_city=False,
        has_bio=False,
        interests_count=0,
        photos_count=0,
        has_preferences=False,
    )
    assert s == 0.0


def test_primary_score_full():
    s = primary_score(
        has_name=True,
        has_age=True,
        has_gender=True,
        has_city=True,
        has_bio=True,
        interests_count=5,
        photos_count=5,
        has_preferences=True,
    )
    assert s == pytest.approx(1.0, abs=1e-6)


def test_primary_score_partial():
    s = primary_score(
        has_name=True,
        has_age=True,
        has_gender=True,
        has_city=False,
        has_bio=False,
        interests_count=0,
        photos_count=2,
        has_preferences=False,
    )
    assert 0 < s < 1


def test_behavioral_score_no_data_neutral_ratio():
    s = behavioral_score(
        likes_received=0, skips_received=0, mutual_matches=0,
        dialogs_started=0, active_hours_count=0,
    )
    # Only ratio component fires (0.5 * 0.3 = 0.15)
    assert s == pytest.approx(0.15, abs=1e-3)


def test_behavioral_score_active_user():
    s = behavioral_score(
        likes_received=100, skips_received=0, mutual_matches=20,
        dialogs_started=10, active_hours_count=24,
    )
    assert s == pytest.approx(1.0, abs=1e-3)


def test_combined_score_referral_capped():
    # huge referral bonus must be capped (cap=0.3)
    s_uncapped_input = combined_score(
        primary=0.5, behavioral=0.5, referral_bonus=10.0, peer_score=0.2
    )
    s_capped_input = combined_score(
        primary=0.5, behavioral=0.5, referral_bonus=0.3, peer_score=0.2
    )
    assert s_uncapped_input == pytest.approx(s_capped_input, abs=1e-9)


def test_combined_score_primary_increases_total():
    low_primary = combined_score(
        primary=0.1, behavioral=0.5, referral_bonus=0.2, peer_score=0.3
    )
    high_primary = combined_score(
        primary=0.9, behavioral=0.5, referral_bonus=0.2, peer_score=0.3
    )
    assert high_primary > low_primary


def test_combined_score_is_bounded_by_five():
    s = combined_score(
        primary=10.0, behavioral=10.0, referral_bonus=10.0, peer_score=10.0
    )
    assert s == pytest.approx(settings.combined_score_max, abs=1e-9)


def test_combined_after_review_good_score_never_decreases():
    old = 3.2
    current = 2.9
    new_value = combined_after_review(
        previous_combined=old,
        current_combined=current,
        review_score=4.5,
    )
    assert new_value == old


def test_combined_after_review_low_score_keeps_current():
    old = 3.2
    current = 2.9
    new_value = combined_after_review(
        previous_combined=old,
        current_combined=current,
        review_score=4.4,
    )
    assert new_value == current


def test_peer_score_formula_penalizes_low_reviews():
    score = peer_score_formula(peer_avg=2.0, peer_count=20)
    assert score < 0


def test_peer_score_formula_rewards_high_reviews():
    score = peer_score_formula(peer_avg=5.0, peer_count=20)
    assert score > 0


def test_peer_score_formula_neutral_at_three():
    score = peer_score_formula(peer_avg=3.0, peer_count=20)
    assert score == pytest.approx(0.0, abs=1e-9)


def test_peer_score_formula_bayesian_smoothing_for_single_review():
    score = peer_score_formula(peer_avg=5.0, peer_count=1)
    # With smoothing and dampening this should be positive, but small.
    assert 0 < score < 0.05


def test_peer_score_formula_full_dampening_after_threshold():
    score = peer_score_formula(peer_avg=5.0, peer_count=int(settings.peer_dampening_threshold))
    assert score > 0.1
