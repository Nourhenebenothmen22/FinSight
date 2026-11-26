"""Health check schemas."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(StrEnum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    """Health check response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "FinSight",
                "version": "0.1.0",
                "environment": "development",
                "checks": {
                    "database": "healthy",
                    "redis": "healthy",
                    "qdrant": "healthy",
                    "storage": "healthy",
                },
            }
        }
    )

    status: HealthStatus = Field(..., description="Overall health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Deployment environment")
    checks: dict[str, str] = Field(
        default_factory=dict,
        description="Individual dependency health checks",
    )
