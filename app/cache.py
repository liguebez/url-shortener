from fastapi import Request
from redis.asyncio import Redis


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
