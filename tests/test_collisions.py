import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import Url
from app.services.urls import KeyGenerationError, create_short_url

LONG_URL = "https://example.com/target"
TAKEN = "AAAAAAA"
FREE = "BBBBBBB"


def _patch_keys(monkeypatch, keys):
    supply = iter(keys)
    monkeypatch.setattr("app.services.urls.random_key", lambda length: next(supply))


async def _seed_taken(session) -> None:
    session.add(Url(short_id=TAKEN, long_url=LONG_URL))
    await session.flush()


async def _count_rows(session) -> int:
    return await session.scalar(select(func.count()).select_from(Url))


async def test_a_collision_is_retried_with_a_fresh_key(session, redis, monkeypatch):
    await _seed_taken(session)
    _patch_keys(monkeypatch, [TAKEN, FREE])

    url = await create_short_url(session, redis, LONG_URL, settings=get_settings())

    assert url.short_id == FREE


async def test_the_retry_persists_exactly_one_new_row(session, redis, monkeypatch):
    await _seed_taken(session)
    _patch_keys(monkeypatch, [TAKEN, FREE])

    await create_short_url(session, redis, LONG_URL, settings=get_settings())

    assert await _count_rows(session) == 2


async def test_the_colliding_attempt_leaves_the_existing_row_untouched(
    session, redis, monkeypatch
):
    await _seed_taken(session)
    _patch_keys(monkeypatch, [TAKEN, FREE])
    new_long_url = "https://example.com/different"

    await create_short_url(session, redis, new_long_url, settings=get_settings())

    existing = await session.get(Url, TAKEN)
    assert existing.long_url == LONG_URL


async def test_the_session_is_still_usable_after_a_collision(
    session, redis, monkeypatch
):
    await _seed_taken(session)
    _patch_keys(monkeypatch, [TAKEN, FREE])

    await create_short_url(session, redis, LONG_URL, settings=get_settings())

    assert await session.get(Url, TAKEN) is not None


async def test_several_consecutive_collisions_still_succeed(
    session, redis, monkeypatch
):
    settings = get_settings()
    await _seed_taken(session)
    _patch_keys(monkeypatch, [TAKEN] * (settings.max_key_retries - 1) + [FREE])

    url = await create_short_url(session, redis, LONG_URL, settings=settings)

    assert url.short_id == FREE


async def test_an_exhausted_key_space_raises(session, redis, monkeypatch):
    await _seed_taken(session)
    monkeypatch.setattr("app.services.urls.random_key", lambda length: TAKEN)

    with pytest.raises(KeyGenerationError):
        await create_short_url(session, redis, LONG_URL, settings=get_settings())


async def test_the_exhaustion_message_names_the_retry_budget(
    session, redis, monkeypatch
):
    settings = get_settings()
    await _seed_taken(session)
    monkeypatch.setattr("app.services.urls.random_key", lambda length: TAKEN)

    with pytest.raises(KeyGenerationError, match=str(settings.max_key_retries)):
        await create_short_url(session, redis, LONG_URL, settings=settings)


async def test_the_retry_budget_is_honoured_exactly(session, redis, monkeypatch):
    settings = get_settings()
    await _seed_taken(session)
    attempts = []

    def counting_key(length):
        attempts.append(length)
        return TAKEN

    monkeypatch.setattr("app.services.urls.random_key", counting_key)

    with pytest.raises(KeyGenerationError):
        await create_short_url(session, redis, LONG_URL, settings=settings)

    assert len(attempts) == settings.max_key_retries


async def test_the_key_length_comes_from_settings(session, redis, monkeypatch):
    settings = get_settings()
    attempts = []

    def recording_key(length):
        attempts.append(length)
        return FREE

    monkeypatch.setattr("app.services.urls.random_key", recording_key)

    await create_short_url(session, redis, LONG_URL, settings=settings)

    assert attempts == [settings.short_id_length]


async def test_exhaustion_persists_nothing(session, redis, monkeypatch):
    await _seed_taken(session)
    monkeypatch.setattr("app.services.urls.random_key", lambda length: TAKEN)

    with pytest.raises(KeyGenerationError):
        await create_short_url(session, redis, LONG_URL, settings=get_settings())

    assert await _count_rows(session) == 1


async def test_an_integrity_error_that_is_not_a_collision_propagates(session, redis):
    with pytest.raises(IntegrityError):
        await create_short_url(session, redis, None, settings=get_settings())


async def test_a_non_collision_failure_is_not_retried(session, redis, monkeypatch):
    attempts = []

    def counting_key(length):
        attempts.append(length)
        return FREE

    monkeypatch.setattr("app.services.urls.random_key", counting_key)

    with pytest.raises(IntegrityError):
        await create_short_url(session, redis, None, settings=get_settings())

    assert len(attempts) == 1
