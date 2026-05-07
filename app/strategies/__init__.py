from __future__ import annotations

from app.strategies.base import CacheStrategy
from app.strategies.cache_aside import CacheAsideStrategy
from app.strategies.write_back import WriteBackStrategy
from app.strategies.write_through import WriteThroughStrategy


def get_strategy(name: str) -> CacheStrategy:
    name = (name or "").strip().lower()
    if name in ("cache_aside", "lazy", "cache-aside", "lazy_loading"):
        return CacheAsideStrategy()
    if name in ("write_through", "wt", "write-through"):
        return WriteThroughStrategy()
    if name in ("write_back", "wb", "write-back"):
        return WriteBackStrategy()
    raise ValueError(f"Unknown CACHE_STRATEGY: {name!r}")


__all__ = ["CacheStrategy", "get_strategy"]
