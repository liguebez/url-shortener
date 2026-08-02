from datetime import UTC, datetime, timedelta

import pytest
from redis import RedisError

from app.cache import GONE, MISSING
from app.models import Url

SHORT_ID = "aB3xY7z"
LONG_URL = "https://example.com/target"


async def _seed(session, **kwargs) -> Url:
    url = Url(
        short_id=kwargs.pop("short_id", SHORT_ID),
        long_url=kwargs.pop("long_url", LONG_URL),
        **kwargs,
    )
    session.add(url)
    await session.flush()
    return url


async def _raise_redis_error(*args, **kwargs):
    raise RedisError("connection refused")


async def test_a_live_url_redirects_with_302(client, session):
    await _seed(session)
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 302


async def test_the_location_header_carries_the_long_url(client, session):
    await _seed(session)
    response = await client.get(f"/{SHORT_ID}")
    assert response.headers["location"] == LONG_URL


async def test_the_redirect_is_not_cacheable(client, session):
    await _seed(session)
    response = await client.get(f"/{SHORT_ID}")
    assert response.headers["cache-control"] == "no-store"


async def test_an_unknown_id_returns_404(client):
    response = await client.get("/zzzzzzz")
    assert response.status_code == 404


async def test_an_expired_url_returns_410(client, session):
    await _seed(session, expires_at=datetime.now(UTC) - timedelta(days=1))
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 410


async def test_a_deleted_url_returns_410(client, session):
    await _seed(session, deleted_at=datetime.now(UTC))
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 410


async def test_a_deleted_url_returns_410_even_with_a_future_expiry(client, session):
    await _seed(
        session,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        deleted_at=datetime.now(UTC),
    )
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 410


async def test_a_future_expiry_still_redirects(client, session):
    await _seed(session, expires_at=datetime.now(UTC) + timedelta(days=7))
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 302


@pytest.mark.parametrize("bad_id", ["abc", "aB3xY7z8", "aB3xY7-", "aB3xY7 "])
async def test_a_malformed_id_returns_404(client, bad_id):
    response = await client.get(f"/{bad_id}")
    assert response.status_code == 404


async def test_a_malformed_id_is_rejected_before_any_cache_write(client, redis):
    await client.get("/abc")
    assert await redis.get("u:abc") is None


async def test_a_successful_lookup_populates_the_cache(client, session, redis):
    await _seed(session)
    await client.get(f"/{SHORT_ID}")
    assert await redis.get(f"u:{SHORT_ID}") == LONG_URL


async def test_a_miss_is_negatively_cached(client, redis):
    await client.get("/zzzzzzz")
    assert await redis.get("u:zzzzzzz") == MISSING


async def test_an_expired_url_is_cached_as_gone(client, session, redis):
    await _seed(session, expires_at=datetime.now(UTC) - timedelta(days=1))
    await client.get(f"/{SHORT_ID}")
    assert await redis.get(f"u:{SHORT_ID}") == GONE


async def test_a_deleted_url_is_cached_as_gone(client, session, redis):
    await _seed(session, deleted_at=datetime.now(UTC))
    await client.get(f"/{SHORT_ID}")
    assert await redis.get(f"u:{SHORT_ID}") == GONE


async def test_a_cache_hit_serves_a_redirect_with_no_row_in_the_database(client, redis):
    await redis.set(f"u:{SHORT_ID}", LONG_URL)
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 302
    assert response.headers["location"] == LONG_URL


async def test_a_cached_missing_sentinel_short_circuits_the_database(
    client, session, redis
):
    await _seed(session)
    await redis.set(f"u:{SHORT_ID}", MISSING)
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 404


async def test_a_cached_gone_sentinel_short_circuits_the_database(
    client, session, redis
):
    await _seed(session)
    await redis.set(f"u:{SHORT_ID}", GONE)
    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 410


async def test_the_cached_ttl_never_outlives_the_url(client, session, redis):
    await _seed(session, expires_at=datetime.now(UTC) + timedelta(seconds=30))
    await client.get(f"/{SHORT_ID}")
    assert 0 < await redis.ttl(f"u:{SHORT_ID}") <= 30


async def test_creating_a_url_clears_a_stale_negative_cache_entry(
    client, redis, monkeypatch
):
    await client.get("/AAAAAAA")
    assert await redis.get("u:AAAAAAA") == MISSING

    monkeypatch.setattr("app.services.urls.random_key", lambda length: "AAAAAAA")
    response = await client.post("/api/urls", json={"long_url": LONG_URL})

    assert response.status_code == 201
    assert await redis.get("u:AAAAAAA") is None


async def test_a_redirect_still_works_when_redis_is_unavailable(
    client, session, redis, monkeypatch
):
    await _seed(session)
    monkeypatch.setattr(redis, "get", _raise_redis_error)
    monkeypatch.setattr(redis, "set", _raise_redis_error)

    response = await client.get(f"/{SHORT_ID}")
    assert response.status_code == 302
    assert response.headers["location"] == LONG_URL
