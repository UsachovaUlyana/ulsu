from __future__ import annotations

import pytest

from app.formulas import (
    behavioral_score,
    combined_score,
    haversine_km,
    primary_score,
)


def test_haversine_zero_distance():
    assert haversine_km(55.75, 37.62, 55.75, 37.62) == pytest.approx(0.0, abs=1e-6)


def test_haversine_moscow_spb():
    # Moscow ~ (55.75, 37.62), SPb ~ (59.93, 30.31). True great-circle ≈ 633 km
    d = haversine_km(55.75, 37.62, 59.93, 30.31)
    assert 600 < d < 700


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
    s_uncapped_input = combined_score(primary=0.5, behavioral=0.5, referral_bonus=10.0)
    s_capped_input = combined_score(primary=0.5, behavioral=0.5, referral_bonus=0.3)
    assert s_uncapped_input == pytest.approx(s_capped_input, abs=1e-9)
