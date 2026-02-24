"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from sample_agent import dependencies
from sample_agent.models.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    client = dependencies.memory_client
    db_connected = client is not None and client.is_connected

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        database="connected" if db_connected else "disconnected",
    )
