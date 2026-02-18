"""Chat request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(min_length=1, max_length=10_000, description="User message text")
    session_id: str | None = Field(default=None, description="Existing session ID")
    user_id: str | None = Field(default=None, description="User identifier")


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    response: str = Field(description="Assistant response text")
    session_id: str = Field(description="Session identifier")
