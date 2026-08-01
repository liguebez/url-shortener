from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Url
from app.utils.base62 import random_key

UNIQUE_VIOLATION = "23505"


class KeyGenerationError(Exception):
    pass


async def create_short_url(
    session: AsyncSession,
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
        session.add(new_url)
        try:
            await session.flush()
            break
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
                raise
            await session.rollback()
    else:
        raise KeyGenerationError(
            f"no unique short_id after {settings.max_key_retries} attempts"
        )

    await session.commit()
    return new_url


def is_gone(url: Url, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return url.deleted_at is not None or (
        url.expires_at is not None and url.expires_at <= now
    )


async def get_url(session: AsyncSession, short_id: str) -> Url | None:

    return await session.get(Url, short_id)
