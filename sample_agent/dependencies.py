"""FastAPI dependency injection for the retail assistant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from neo4j_agent_memory import MemoryClient

from sample_agent.models.session import Session

# Module-level state managed by the app lifespan.
memory_client: MemoryClient | None = None


def get_client() -> MemoryClient:
    """Get the connected MemoryClient or raise 503."""
    if not memory_client or not memory_client.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")
    return memory_client


def get_db() -> Any:
    """Get the Neo4j graph client for direct Cypher queries."""
    return get_client().graph


# NOTE: MemoryClient does not expose a public embedder property.
# Accessing _embedder is the only way to get the embedding provider.
def get_embedder() -> Any:
    """Get the embedding provider."""
    return get_client()._embedder


# --- Session Management ---

sessions: dict[str, Session] = {}


def get_or_create_session(session_id: str | None, user_id: str | None = None) -> str:
    """Get existing session or create new one."""
    if session_id and session_id in sessions:
        return session_id

    new_session_id = session_id or str(uuid4())
    sessions[new_session_id] = Session(
        user_id=user_id,
        created_at=datetime.now(UTC),
    )
    return new_session_id
