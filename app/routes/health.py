import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


RedisDep = Annotated[Redis, Depends(get_redis)]

CHECK_TIMEOUT_SECONDS = 2.0


async def _check_database(session: AsyncSession) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database health check failed: %s", exc)
        return False
    return True


async def _check_redis(redis: Redis) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await redis.ping()
    except Exception as exc:
        logger.warning("redis health check failed: %s", exc)
        return False
    return True


@router.get(
    "/healthz",
    responses={
        200: {"description": "All dependencies reachable"},
        503: {"description": "One or more dependencies unreachable"},
    },
)
async def healthz(session: SessionDep, redis: RedisDep) -> JSONResponse:
    database_ok, redis_ok = await asyncio.gather(
        _check_database(session),
        _check_redis(redis),
    )
    healthy = database_ok and redis_ok
    return JSONResponse(
        status_code=status.HTTP_200_OK
        if healthy
        else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if healthy else "degraded",
            "checks": {
                "database": "ok" if database_ok else "error",
                "redis": "ok" if redis_ok else "error",
            },
        },
    )
