import pytest

from app.verifier.cache import TTLCache


@pytest.mark.asyncio
async def test_set_get_roundtrip() -> None:
    cache: TTLCache[str] = TTLCache()
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_expiry() -> None:
    cache: TTLCache[str] = TTLCache(ttl_seconds=-1)
    await cache.set("k", "v")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_lru_eviction() -> None:
    cache: TTLCache[int] = TTLCache(max_entries=2)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.get("a")  # touch a so b is the LRU
    await cache.set("c", 3)  # evicts b
    assert await cache.get("b") is None
    assert await cache.get("a") == 1
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_get_or_compute_caches() -> None:
    cache: TTLCache[int] = TTLCache()
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await cache.get_or_compute("k", factory) == 42
    assert await cache.get_or_compute("k", factory) == 42
    assert calls == 1
