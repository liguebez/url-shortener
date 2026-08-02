import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Base

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]


async def _create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _drop_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def engine() -> AsyncEngine:
    return create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def _schema(engine: AsyncEngine) -> Iterator[None]:
    asyncio.run(_create_all(engine))
    yield
    asyncio.run(_drop_all(engine))


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        db_session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            if trans.is_active:
                await trans.rollback()


@pytest.fixture
async def redis() -> AsyncIterator[FakeRedis]:
    fake = FakeRedis(decode_responses=True)
    try:
        yield fake
    finally:
        await fake.flushall()
        await fake.aclose()


@pytest.fixture
async def client(
    session: AsyncSession,
    redis: FakeRedis,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
