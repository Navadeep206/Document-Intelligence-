"""Health and readiness probe endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
import redis

from app.core.config import get_settings
from app.db.database import check_db_health

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()

router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness probe response model."""

    status: Literal["healthy"] = Field(
        default="healthy", description="Service liveness state"
    )
    service: str = Field(
        default=settings.APP_NAME, description="Canonical service name"
    )


class ReadinessResponse(BaseModel):
    """Readiness probe response model inspecting critical dependencies."""

    status: Literal["ready", "unhealthy"] = Field(
        description="Overall service readiness state"
    )
    database: Literal["healthy", "unhealthy"] = Field(
        description="PostgreSQL connectivity state"
    )
    redis: Literal["healthy", "unhealthy"] = Field(
        description="Redis broker/backend connectivity state"
    )


def check_redis_health(redis_url: str) -> tuple[bool, str]:
    """Verify Redis broker reachability via a lightweight ping."""
    client = None
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        if client.ping():
            return True, "healthy"
        return False, "unhealthy"
    except Exception as exc:
        logger.error("Redis health probe connection failed: %s", exc)
        return False, "unhealthy"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Liveness Probe",
    description="Returns the immediate liveness status of the FastAPI web application.",
)
async def liveness() -> HealthResponse:
    """Check service liveness."""
    return HealthResponse(status="healthy", service=settings.APP_NAME)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "One or more infrastructure dependencies are unavailable",
        }
    },
    summary="Service Readiness Probe",
    description="Validates active connectivity to PostgreSQL and Redis infrastructure components.",
)
async def readiness(response: Response) -> ReadinessResponse:
    """Check overall readiness by pinging database and Redis instances."""
    db_ok, db_status = check_db_health()
    redis_ok, redis_status = check_redis_health(settings.REDIS_URL)

    is_ready = db_ok and redis_ok
    status_value: Literal["ready", "unhealthy"] = "ready" if is_ready else "unhealthy"
    db_status_val: Literal["healthy", "unhealthy"] = "healthy" if db_ok else "unhealthy"
    redis_status_val: Literal["healthy", "unhealthy"] = "healthy" if redis_ok else "unhealthy"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=status_value,
        database=db_status_val,
        redis=redis_status_val,
    )
