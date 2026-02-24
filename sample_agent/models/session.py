"""Session tracking model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Session(BaseModel):
    """Tracked session."""

    user_id: str | None = None
    created_at: datetime
