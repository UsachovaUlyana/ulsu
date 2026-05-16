"""Prometheus metric helpers.

`setup_fastapi_metrics(app)` wires `/metrics` for HTTP services.
The Counter/Histogram/Gauge factories below give every service a uniform
naming scheme for business metrics so the Grafana dashboard works for all.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Business counters
swipes_total = Counter(
    "dating_swipes_total",
    "Total swipes processed",
    ["action"],
)
matches_total = Counter(
    "dating_matches_total",
    "Total mutual matches created",
)
registrations_total = Counter(
    "dating_registrations_total",
    "Total user registrations completed",
)
referrals_applied_total = Counter(
    "dating_referrals_applied_total",
    "Total successful referral applications",
)
icebreaker_sent_total = Counter(
    "dating_icebreaker_sent_total",
    "Total icebreaker messages sent",
    ["category"],
)
likes_notified_total = Counter(
    "dating_likes_notified_total",
    "Total one-way like notifications sent",
)

feed_response_seconds = Histogram(
    "dating_feed_response_seconds",
    "Latency of feed endpoint",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
recalc_duration_seconds = Histogram(
    "dating_recalc_duration_seconds",
    "Duration of rating recalculation tasks",
    ["level"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

active_users_24h = Gauge(
    "dating_active_users_24h",
    "Users with activity in the last 24h",
)
feed_cache_size = Gauge(
    "dating_feed_cache_size",
    "Number of cached feed keys in Redis",
)


def setup_fastapi_metrics(app) -> None:
    """Attach Prometheus middleware + /metrics to a FastAPI app."""
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
