"""Process-local TTL cache for F3 verification results (research.md §12.8).

The same DOI/title is frequently verified across jobs (and within a job when a
paper cites the same work twice). A small async-safe TTL cache avoids redundant
Crossref/OpenAlex/doi.org round-trips. This is intentionally in-process so the
serverless demo needs no external store; the interface mirrors what a Redis
implementation would expose, so it can be swapped later.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from functools import lru_cache

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_ENTRIES = 2048


class TTLCache[V]:
    """Bounded async-safe TTL cache (LRU eviction)."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> V | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: V) -> None:
        async with self._lock:
            self._store[key] = (time.time() + self._ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    async def get_or_compute(self, key: str, factory):
        """Return a cached value or compute, store, and return it.

        ``factory`` is an async callable. Computation happens outside the lock so
        concurrent misses for *different* keys do not serialise on each other.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory()
        if value is not None:
            await self.set(key, value)
        return value

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


@lru_cache
def get_verification_cache() -> TTLCache:
    """Shared cache for VerifiedItem results keyed by a verification signature."""
    return TTLCache()
