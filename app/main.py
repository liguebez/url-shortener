import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache import create_redis
from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.state.engine = make_engine(settings)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.redis = create_redis(settings.redis_url)
    try:
        yield
    finally:
        try:
            await app.state.redis.aclose()
        finally:
            await app.state.engine.dispose()


app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
