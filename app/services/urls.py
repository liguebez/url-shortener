from datetime import UTC, datetime
from enum import StrEnum

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import GONE, MISSING, cache_ttl_for, get_cached, invalidate, set_cached
from app.config import Settings
from app.models import Url
from app.utils.base62 import random_key

UNIQUE_VIOLATION = "23505"


class KeyGenerationError(Exception):
    pass


class Resolution(StrEnum):
    FOUND = "found"
    MISSING = "missing"
    GONE = "gone"


async def resolve_short_id(
    session: AsyncSession,
    redis: Redis,
    short_id: str,
    *,
    settings: Settings,
) -> tuple[Resolution, str | None]:
    cached = await get_cached(redis, short_id)
    if cached == MISSING:
        return (Resolution.MISSING, None)
    if cached == GONE:
        return (Resolution.GONE, None)
    if cached is not None:
        return (Resolution.FOUND, cached)

    url = await get_url(session, short_id)
    if url is None:
        await set_cached(
            redis, short_id, value=MISSING, ttl=settings.negative_cache_ttl_seconds
        )
        return (Resolution.MISSING, None)

    now = datetime.now(UTC)
    ttl = cache_ttl_for(url.expires_at, cache_ttl=settings.cache_ttl_seconds, now=now)
    if is_gone(url, now=now) or ttl <= 0:
        await set_cached(
            redis, short_id, value=GONE, ttl=settings.negative_cache_ttl_seconds
        )
        return (Resolution.GONE, None)

    await set_cached(redis, short_id, value=url.long_url, ttl=ttl)

    return (Resolution.FOUND, url.long_url)


async def create_short_url(
    session: AsyncSession,
    redis: Redis,
    long_url: str,
    *,
    settings: Settings,
    expires_at: datetime | None = None,
    user_id: str | None = None,
) -> Url:
    for _ in range(settings.max_key_retries):
        key = random_key(settings.short_id_length)
        new_url = Url(
            short_id=key, long_url=long_url, user_id=user_id, expires_at=expires_at
        )
        try:
            async with session.begin_nested():
                session.add(new_url)
                await session.flush()
            break
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
                raise
    else:
        raise KeyGenerationError(
            f"no unique short_id after {settings.max_key_retries} attempts"
        )

    await session.commit()
    await invalidate(redis, key)

    return new_url


def is_gone(url: Url, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return url.deleted_at is not None or (
        url.expires_at is not None and url.expires_at <= now
    )


async def get_url(session: AsyncSession, short_id: str) -> Url | None:

    return await session.get(Url, short_id)
