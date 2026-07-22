import pytest

from preview_cache import PreviewCache


@pytest.mark.unit
def test_lru_hit_miss_and_eviction():
    cache = PreviewCache(max_size=2)
    # put/get store arbitrary objects; use sentinels (no Qt needed)
    cache.put("a", object())
    cache.put("b", object())
    assert cache.get("a") is not None          # hit, marks 'a' most-recent
    assert cache.get("missing") is None        # miss
    cache.put("c", object())                    # exceeds max_size -> evict LRU ('b')
    assert cache.get("b") is None               # 'b' evicted
    assert cache.get("a") is not None           # 'a' survived
    assert cache.cache_stats["evictions"] == 1
    assert cache.cache_stats["hits"] >= 2
    assert cache.cache_stats["misses"] >= 2


@pytest.mark.unit
def test_clear_resets_stats():
    cache = PreviewCache(max_size=4)
    cache.put("a", object())
    cache.get("a")
    cache.clear()
    assert cache.get("a") is None
    assert cache.cache_stats["evictions"] == 0
