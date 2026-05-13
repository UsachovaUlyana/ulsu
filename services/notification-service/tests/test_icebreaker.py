from __future__ import annotations

from app.icebreaker import FALLBACK, TEMPLATES, pick_topics


def test_pick_topics_common_interest():
    topics, category = pick_topics(["music", "sport"], ["music"])
    assert category == "music"
    assert len(topics) == 3
    assert all(t in TEMPLATES["music"] for t in topics)


def test_pick_topics_no_common():
    topics, category = pick_topics(["music"], ["food"])
    # both exist as keys but not common → fallback
    # (they only become common when overlap exists)
    assert category == "fallback"
    assert len(topics) == 3
    assert all(t in FALLBACK for t in topics)


def test_pick_topics_empty():
    topics, category = pick_topics(None, None)
    assert category == "fallback"
    assert len(topics) == 3


def test_pick_topics_unknown_interest_falls_back():
    topics, category = pick_topics(["xenoarchaeology"], ["xenoarchaeology"])
    # not in TEMPLATES → falls back
    assert category == "fallback"


def test_topics_unique_within_set():
    topics, _ = pick_topics(["music"], ["music"])
    assert len(set(topics)) == len(topics)
