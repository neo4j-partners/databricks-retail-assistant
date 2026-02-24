"""Memory-related response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryContextResponse(BaseModel):
    """Memory context for the current session."""

    history: str = Field(default="", description="Formatted conversation history")
    context: str = Field(default="", description="Long-term entity and fact context")
    preferences: list[dict[str, str]] = Field(
        default_factory=list, description="Matched user preferences"
    )
    similar_tasks: str = Field(default="", description="Formatted reasoning traces")


class GraphNodeResponse(BaseModel):
    """A node in the memory graph."""

    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelationshipResponse(BaseModel):
    """A relationship in the memory graph."""

    id: str
    type: str
    from_node: str
    to_node: str
    properties: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphResponse(BaseModel):
    """Memory graph for visualization."""

    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    relationships: list[GraphRelationshipResponse] = Field(default_factory=list)


class PreferenceItem(BaseModel):
    """A single user preference."""

    category: str
    preference: str
    context: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PreferencesResponse(BaseModel):
    """User preferences response."""

    preferences: list[PreferenceItem] = Field(default_factory=list)
