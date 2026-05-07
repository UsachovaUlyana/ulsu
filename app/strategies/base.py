from __future__ import annotations

from abc import ABC, abstractmethod


class CacheStrategy(ABC):
    name: str = "base"

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def reset(self) -> None:
        return None

    @abstractmethod
    async def get(self, item_id: int) -> dict | None: ...

    @abstractmethod
    async def set(self, item_id: int, payload: str) -> None: ...
