"""Shared asynchronous Redis client lifecycle and FastAPI dependency."""

from dataclasses import dataclass

import redis.asyncio as aioredis

from app.core.config import get_settings


@dataclass
class _RedisState:
    client: aioredis.Redis | None = None


_state = _RedisState()


def get_redis_client() -> aioredis.Redis:
    """Get or lazily initialize the shared async Redis client."""
    if _state.client is None:
        settings = get_settings()
        _state.client = aioredis.from_url(
            str(settings.REDIS_URL),
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    return _state.client


async def close_redis() -> None:
    """Close shared Redis client cleanly."""
    if _state.client is not None:
        await _state.client.aclose()
        _state.client = None


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency returning the async Redis client."""
    return get_redis_client()
