"""Canonical RabbitMQ exchange / routing-key constants and event payload types.

Single source of truth — every publisher and consumer imports from here so
typos in topic names don't quietly break message delivery.
"""

from __future__ import annotations

# Exchanges (one topic exchange per event family)
EXCHANGE_SWIPES = "swipe_events"
EXCHANGE_MATCHES = "match_events"
EXCHANGE_PROFILES = "profile_events"
EXCHANGE_REFERRALS = "referral_events"
EXCHANGE_REVIEWS = "review_events"

# Routing keys
RK_SWIPE_CREATED = "swipe.created"
RK_MATCH_CREATED = "match.created"
RK_PROFILE_UPDATED = "profile.updated"
RK_REFERRAL_APPLIED = "referral.applied"
RK_PROFILE_DELETED = "profile.deleted"
RK_LIKE_RECEIVED = "like.received"
RK_REVIEW_CREATED = "review.created"
RK_REVIEW_UPDATED = "review.updated"

ALL_EXCHANGES = (
    EXCHANGE_SWIPES,
    EXCHANGE_MATCHES,
    EXCHANGE_PROFILES,
    EXCHANGE_REFERRALS,
    EXCHANGE_REVIEWS,
)
