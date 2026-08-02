import logging
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from redis import RedisError
from redis.asyncio import Redis

KEY_PREFIX = "u:"
MISSING = "\x00missing"
GONE = "\x00gone"

logger = logging.getLogger(__name__)


def create_redis(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.25,
        max_connections=50,
        health_check_interval=30,
        retry_on_timeout=False,
    )


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]


def key_for(short_id: str) -> str:
    return f"{KEY_PREFIX}{short_id}"


def cache_ttl_for(expires_at: datetime | None, *, cache_ttl: int, now: datetime) -> int:
    if expires_at is None:
        return cache_ttl

    seconds_left = int((expires_at - now).total_seconds())

    if seconds_left <= 0:
        return 0

    return min(cache_ttl, seconds_left)


async def get_cached(redis: Redis, short_id: str) -> str | None:
    try:
        res = await redis.get(key_for(short_id))
        return res
    except RedisError as exc:
        logger.warning("cache read failed for %s: %s", short_id, exc)
        return None


async def set_cached(redis: Redis, short_id: str, value: str, ttl: int) -> None:
    try:
        await redis.set(key_for(short_id), value, ex=ttl)
    except RedisError as exc:
        logger.warning("cache set failed for %s: %s", short_id, exc)


async def invalidate(redis: Redis, short_id: str) -> None:
    try:
        await redis.delete(key_for(short_id))
    except RedisError as exc:
        logger.warning("cache delete failed for %s: %s", short_id, exc)
