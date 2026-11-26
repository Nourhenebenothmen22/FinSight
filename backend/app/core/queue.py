"""Background task queue abstraction backed by ARQ."""

from dataclasses import dataclass
from typing import Protocol

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class TaskDispatcher(Protocol):
    """Protocol for dispatching asynchronous background tasks."""

    async def enqueue(self, task_name: str, *args: object) -> None:
        """Schedule a background task by name."""


class ArqTaskDispatcher:
    """ARQ-backed task dispatcher."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue(self, task_name: str, *args: object) -> None:
        """Enqueue an ARQ job."""
        await self._pool.enqueue_job(task_name, *args)


@dataclass
class _QueueState:
    pool: ArqRedis | None = None


_queue_state = _QueueState()


def build_arq_redis_settings() -> RedisSettings:
    """Build ARQ RedisSettings from application configuration."""
    settings = get_settings()
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD.get_secret_value() or None,
        database=settings.REDIS_DB,
    )


async def get_arq_pool() -> ArqRedis:
    """Get or create the shared ARQ Redis pool."""
    if _queue_state.pool is None:
        _queue_state.pool = await create_pool(build_arq_redis_settings())
    return _queue_state.pool


async def close_arq_pool() -> None:
    """Close shared ARQ Redis pool."""
    if _queue_state.pool is not None:
        await _queue_state.pool.close()
        _queue_state.pool = None


async def get_task_dispatcher() -> TaskDispatcher:
    """FastAPI dependency providing the background task dispatcher."""
    pool = await get_arq_pool()
    return ArqTaskDispatcher(pool)
