"""FinSight ARQ background worker skeleton (F0 foundation)."""

from typing import Any

import structlog
from arq.connections import RedisSettings

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Minimal F0 health/smoke job for the background worker."""
    _ = ctx
    return "pong"


async def on_startup(ctx: dict[str, Any]) -> None:
    """Worker startup lifecycle hook."""
    settings = get_settings()
    ctx["app_env"] = settings.APP_ENV
    logger.info("worker.startup", environment=settings.APP_ENV)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown lifecycle hook."""
    _ = ctx
    logger.info("worker.shutdown")


def get_redis_settings() -> RedisSettings:
    """Build ARQ RedisSettings from application configuration."""
    settings = get_settings()
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD.get_secret_value() or None,
        database=settings.REDIS_DB,
    )


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [ping]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = get_redis_settings()
