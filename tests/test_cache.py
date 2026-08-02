from datetime import UTC, datetime, timedelta

from redis import RedisError

from app.cache import (
    GONE,
    MISSING,
    cache_ttl_for,
    get_cached,
    invalidate,
    key_for,
    set_cached,
)

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
CACHE_TTL = 3600
SHORT_ID = "aB3xY7z"
LONG_URL = "https://example.com/target"


async def _raise_redis_error(*args, **kwargs):
    raise RedisError("connection refused")


def test_keys_are_namespaced():
    assert key_for(SHORT_ID) == f"u:{SHORT_ID}"


def test_sentinels_are_not_valid_urls():
    assert MISSING.startswith("\x00")
    assert GONE.startswith("\x00")
    assert MISSING != GONE


def test_absent_expiry_uses_the_full_cache_ttl():
    assert cache_ttl_for(None, cache_ttl=CACHE_TTL, now=NOW) == CACHE_TTL


def test_distant_expiry_is_clamped_to_the_cache_ttl():
    far = NOW + timedelta(days=30)
    assert cache_ttl_for(far, cache_ttl=CACHE_TTL, now=NOW) == CACHE_TTL


def test_near_expiry_shortens_the_ttl():
    soon = NOW + timedelta(seconds=120)
    assert cache_ttl_for(soon, cache_ttl=CACHE_TTL, now=NOW) == 120


def test_expiry_exactly_at_the_cache_ttl_boundary():
    edge = NOW + timedelta(seconds=CACHE_TTL)
    assert cache_ttl_for(edge, cache_ttl=CACHE_TTL, now=NOW) == CACHE_TTL


def test_expiry_at_now_yields_zero():
    assert cache_ttl_for(NOW, cache_ttl=CACHE_TTL, now=NOW) == 0


def test_past_expiry_yields_zero():
    past = NOW - timedelta(days=1)
    assert cache_ttl_for(past, cache_ttl=CACHE_TTL, now=NOW) == 0


def test_sub_second_remaining_truncates_to_zero():
    almost = NOW + timedelta(milliseconds=900)
    assert cache_ttl_for(almost, cache_ttl=CACHE_TTL, now=NOW) == 0


async def test_set_then_get_round_trips(redis):
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)
    assert await get_cached(redis, SHORT_ID) == LONG_URL


async def test_get_returns_none_for_an_unknown_key(redis):
    assert await get_cached(redis, SHORT_ID) is None


async def test_values_are_stored_under_the_prefixed_key(redis):
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)
    assert await redis.get(f"u:{SHORT_ID}") == LONG_URL
    assert await redis.get(SHORT_ID) is None


async def test_the_ttl_is_applied_to_the_entry(redis):
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)
    assert 0 < await redis.ttl(f"u:{SHORT_ID}") <= 60


async def test_reads_come_back_as_str_not_bytes(redis):
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)
    assert isinstance(await get_cached(redis, SHORT_ID), str)


async def test_sentinels_survive_a_round_trip(redis):
    await set_cached(redis, "missing1", value=MISSING, ttl=60)
    await set_cached(redis, "gone123", value=GONE, ttl=60)
    assert await get_cached(redis, "missing1") == MISSING
    assert await get_cached(redis, "gone123") == GONE


async def test_invalidate_removes_the_entry(redis):
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)
    await invalidate(redis, SHORT_ID)
    assert await get_cached(redis, SHORT_ID) is None


async def test_invalidate_is_a_noop_for_absent_keys(redis):
    await invalidate(redis, SHORT_ID)
    assert await get_cached(redis, SHORT_ID) is None


async def test_get_degrades_to_none_when_redis_fails(redis, monkeypatch):
    monkeypatch.setattr(redis, "get", _raise_redis_error)
    assert await get_cached(redis, SHORT_ID) is None


async def test_set_swallows_redis_failures(redis, monkeypatch):
    monkeypatch.setattr(redis, "set", _raise_redis_error)
    await set_cached(redis, SHORT_ID, value=LONG_URL, ttl=60)


async def test_invalidate_swallows_redis_failures(redis, monkeypatch):
    monkeypatch.setattr(redis, "delete", _raise_redis_error)
    await invalidate(redis, SHORT_ID)
