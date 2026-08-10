from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    value: T
    expires_at: float
    fetched_at: float


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: dict[str, CacheEntry[T]] = {}

    def get_fresh(self, key: str) -> CacheEntry[T] | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if time.time() >= entry.expires_at:
            return None
        return entry

    def get_any(self, key: str) -> CacheEntry[T] | None:
        return self._data.get(key)

    def set(self, key: str, value: T) -> CacheEntry[T]:
        now = time.time()
        entry = CacheEntry(value=value, expires_at=now + self.ttl_seconds, fetched_at=now)
        self._data[key] = entry
        return entry
