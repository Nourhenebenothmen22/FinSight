"""Health check endpoints."""

import asyncio

import httpx
import redis.asyncio as redis
import structlog
import urllib3
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.schemas.health import HealthResponse, HealthStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


async def _check_database(db: AsyncSession) -> str:
    """Check PostgreSQL connectivity."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("healthcheck.database_failed")
        return "unhealthy"
    else:
        return "healthy"


async def _check_redis(settings: Settings) -> str:
    """Check Redis connectivity."""
    client = redis.from_url(
        str(settings.REDIS_URL),
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    try:
        await client.ping()
    except Exception:
        logger.exception("healthcheck.redis_failed")
        return "unhealthy"
    else:
        return "healthy"
    finally:
        await client.aclose()


async def _check_qdrant(settings: Settings) -> str:
    """Check Qdrant readiness."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.QDRANT_URL}/readyz")
    except Exception:
        logger.exception("healthcheck.qdrant_failed")
        return "unhealthy"
    else:
        if resp.status_code == status.HTTP_200_OK:
            return "healthy"
        logger.warning("healthcheck.qdrant_unhealthy", status_code=resp.status_code)
        return "unhealthy"


def _check_storage_sync(settings: Settings) -> str:
    """Verify S3-compatible storage connectivity and configured buckets."""
    http_client = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=2.0, read=2.0),
        retries=False,
    )
    client = Minio(
        settings.S3_ENDPOINT,
        access_key=settings.S3_ACCESS_KEY.get_secret_value(),
        secret_key=settings.S3_SECRET_KEY.get_secret_value(),
        secure=settings.S3_SECURE,
        region=settings.S3_REGION,
        http_client=http_client,
    )
    required_buckets = (
        settings.S3_BUCKET_DOCUMENTS,
        settings.S3_BUCKET_REPORTS,
    )
    for bucket in required_buckets:
        if not client.bucket_exists(bucket):
            logger.warning("healthcheck.storage_missing_bucket", bucket=bucket)
            return "unhealthy"
    return "healthy"


async def _check_storage(settings: Settings) -> str:
    """Check S3-compatible object storage asynchronously."""
    try:
        return await asyncio.to_thread(_check_storage_sync, settings)
    except Exception:
        logger.exception("healthcheck.storage_failed")
        return "unhealthy"


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the health status of the API and its dependencies.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse,
            "description": "One or more dependencies are unhealthy",
        }
    },
)
async def health_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Check health of API and all required dependencies."""
    db_status = await _check_database(db)
    redis_status, qdrant_status, storage_status = await asyncio.gather(
        _check_redis(settings),
        _check_qdrant(settings),
        _check_storage(settings),
    )

    checks: dict[str, str] = {
        "database": db_status,
        "redis": redis_status,
        "qdrant": qdrant_status,
        "storage": storage_status,
    }

    overall_status = (
        HealthStatus.HEALTHY
        if all(value == "healthy" for value in checks.values())
        else HealthStatus.UNHEALTHY
    )

    payload = HealthResponse(
        status=overall_status,
        service=settings.APP_NAME,
        version="0.1.0",
        environment=settings.APP_ENV,
        checks=checks,
    )

    http_status = (
        status.HTTP_200_OK
        if overall_status == HealthStatus.HEALTHY
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=http_status, content=payload.model_dump(mode="json"))


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness check",
    description="Readiness probe - checks if service and dependencies can accept traffic.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse,
            "description": "Service is not ready",
        }
    },
)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Readiness probe."""
    return await health_check(db=db, settings=settings)


@router.get(
    "/live",
    summary="Liveness check",
    description="Liveness probe - checks if process is alive.",
)
async def liveness_check() -> dict[str, str]:
    """Liveness probe - minimal check."""
    return {"status": "alive"}
