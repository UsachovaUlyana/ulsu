from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Profile:
    name: str
    read_ratio: float


PROFILES = [
    Profile("read_heavy", 0.8),
    Profile("balanced", 0.5),
    Profile("write_heavy", 0.2),
]


class ZipfKeySpace:
    """Skewed key sampling, gives realistic hit-rate variance."""

    def __init__(self, n_keys: int, alpha: float = 1.2, seed: int | None = None) -> None:
        self.n_keys = n_keys
        self.alpha = alpha
        self.rng = np.random.default_rng(seed)

    def next_key(self) -> int:
        while True:
            v = int(self.rng.zipf(self.alpha))
            if 1 <= v <= self.n_keys:
                return v


def random_payload(size: int = 256) -> str:
    return "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=size))


def pick_op(read_ratio: float) -> str:
    return "read" if random.random() < read_ratio else "write"
