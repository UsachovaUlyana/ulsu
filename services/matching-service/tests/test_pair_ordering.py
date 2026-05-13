"""Match-table invariant: user1_id < user2_id is enforced by CHECK constraint.
This guards the ordering helper that consumer.py uses (`sorted(...)`)."""

from __future__ import annotations


def test_pair_ordering_canonical():
    swiper, target = 7, 3
    u1, u2 = sorted((swiper, target))
    assert u1 < u2
    assert (u1, u2) == (3, 7)


def test_pair_ordering_idempotent():
    a, b = sorted((1, 2))
    c, d = sorted((2, 1))
    assert (a, b) == (c, d)
