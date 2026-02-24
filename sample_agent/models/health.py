"""Health check response model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "degraded"]
    database: Literal["connected", "disconnected"]
