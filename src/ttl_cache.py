"""Small async in-memory TTL cache utility."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

_MISSING = object()


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Async-safe in-memory TTL cache for simple server-local values."""

    def __init__(self) -> None:
        self._data: dict[Hashable, _CacheEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._key_locks: dict[Hashable, asyncio.Lock] = {}

    async def get(self, key: Hashable) -> T | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                self._data.pop(key, None)
                return None
            return entry.value

    async def set(self, key: Hashable, value: T, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        expires_at = time.monotonic() + ttl_seconds
        async with self._lock:
            self._data[key] = _CacheEntry(value=value, expires_at=expires_at)

    async def get_or_set(
        self,
        key: Hashable,
        ttl_seconds: float,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        cached = await self.get(key)
        if cached is not None:
            return cached

        key_lock = await self._get_key_lock(key)
        async with key_lock:
            cached = await self.get(key)
            if cached is not None:
                return cached

            value = await loader()
            await self.set(key, value, ttl_seconds)
            return value

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
            self._key_locks.clear()

    async def _get_key_lock(self, key: Hashable) -> asyncio.Lock:
        async with self._lock:
            stale = [
                k
                for k in self._key_locks
                if k != key
                and not self._key_locks[k].locked()
                and (
                    k not in self._data
                    or self._data[k].expires_at <= time.monotonic()
                )
            ]
            for k in stale:
                del self._key_locks[k]

            existing = self._key_locks.get(key, _MISSING)
            if existing is not _MISSING:
                return existing  # type: ignore[return-value]
            lock = asyncio.Lock()
            self._key_locks[key] = lock
            return lock
