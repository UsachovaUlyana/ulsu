"""Чистые функции расчёта рейтинга. Без I/O — для удобства unit-тестов."""

from __future__ import annotations

from .config import settings

# ---------------- L1 — primary ----------------


def primary_score(
    *,
    has_name: bool,
    has_age: bool,
    has_gender: bool,
    has_city: bool,
    has_bio: bool,
    interests_count: int,
    photos_count: int,
    has_preferences: bool,
) -> float:
    completeness_filled = sum([has_name, has_age, has_gender, has_city, has_bio])
    completeness = (completeness_filled + min(interests_count, 5) / 5) / 6
    photos = min(photos_count, 5) / 5
    prefs = 1.0 if has_preferences else 0.0
    return (
        settings.w_l1_completeness * completeness
        + settings.w_l1_photos * photos
        + settings.w_l1_prefs * prefs
    )


# ---------------- L2 — behavioral ----------------


def _cap(x: float, ceiling: float = 1.0) -> float:
    return max(0.0, min(ceiling, x))


def behavioral_score(
    *,
    likes_received: int,
    skips_received: int,
    mutual_matches: int,
    dialogs_started: int,
    active_hours_count: int,  # уникальных часов активности за окно
) -> float:
    # Each component normalised to [0,1].
    likes_norm = _cap(likes_received / 100.0)
    total = likes_received + skips_received
    ratio = (likes_received / total) if total else 0.5  # neutral until we have data
    mutual = _cap(mutual_matches / 20.0)
    dialog = _cap(dialogs_started / 10.0)
    activity = _cap(active_hours_count / 24.0)

    return (
        settings.w_l2_likes_received * likes_norm
        + settings.w_l2_like_ratio * ratio
        + settings.w_l2_mutual * mutual
        + settings.w_l2_dialog * dialog
        + settings.w_l2_activity * activity
    )


# ---------------- L3 — combined ----------------


def peer_score_formula(peer_avg: float | None, peer_count: int) -> float:
    if peer_avg is None or peer_count == 0:
        return 0.0

    # Bayesian smoothing so 1-2 reviews don't swing the score too hard.
    smoothed_avg = (
        peer_avg * peer_count
        + settings.peer_prior_mean * settings.peer_prior_weight
    ) / (peer_count + settings.peer_prior_weight)

    # 3.0 is neutral. <3 decreases ranking, >3 increases it.
    peer_normalized = (smoothed_avg - 3.0) / 2.0
    peer_normalized = max(-1.0, min(1.0, peer_normalized))
    dampening = min(peer_count / settings.peer_dampening_threshold, 1.0)
    return peer_normalized * dampening


def combined_score(
    primary: float,
    behavioral: float,
    referral_bonus: float,
    peer_score: float = 0.0,
) -> float:
    primary_norm = _cap(primary)
    behavioral_norm = _cap(behavioral)
    peer_norm = _cap(peer_score)
    bonus_capped = _cap(referral_bonus, settings.referral_bonus_cap)
    if settings.referral_bonus_cap > 0:
        referral_norm = bonus_capped / settings.referral_bonus_cap
    else:
        referral_norm = 0.0

    score = (
        settings.combined_profile_part_max * primary_norm
        + settings.combined_behavioral_part_max * behavioral_norm
        + settings.combined_peer_part_max * peer_norm
        + settings.combined_referral_part_max * referral_norm
    )
    return _cap(score, settings.combined_score_max)


def combined_after_review(
    *,
    previous_combined: float,
    current_combined: float,
    review_score: float,
) -> float:
    if review_score >= settings.good_review_threshold:
        return max(previous_combined, current_combined)
    return current_combined
