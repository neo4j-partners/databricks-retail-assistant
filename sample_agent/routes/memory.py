"""Memory endpoints backed by Neo4j Agent Memory."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from neo4j_agent_memory import MemoryClient
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory

from sample_agent.dependencies import get_client
from sample_agent.models.memory import (
    GraphNodeResponse,
    GraphRelationshipResponse,
    MemoryContextResponse,
    MemoryGraphResponse,
    PreferenceItem,
    PreferencesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

Client = Annotated[MemoryClient, Depends(get_client)]


def _get_agent_memory(client: MemoryClient, session_id: str) -> Neo4jAgentMemory:
    """Create a Neo4jAgentMemory bound to a session."""
    return Neo4jAgentMemory(
        memory_client=client,
        session_id=session_id,
        include_short_term=True,
        include_long_term=True,
        include_reasoning=True,
    )


@router.get("/context", response_model=MemoryContextResponse)
async def get_memory_context(
    client: Client,
    session_id: str = Query(..., description="Session ID"),
    query: str = Query("", description="Query for relevant context"),
) -> MemoryContextResponse:
    """Get current memory context for a session."""
    try:
        memory = _get_agent_memory(client, session_id)
        result = await memory._load_memory_variables_async({"input": query})
        return MemoryContextResponse(
            history=result.get("history", ""),
            context=result.get("context", ""),
            preferences=result.get("preferences", []),
            similar_tasks=result.get("similar_tasks", ""),
        )
    except Exception:
        logger.exception("Error loading memory context")
        raise HTTPException(status_code=500, detail="Failed to load memory context")


@router.get("/graph", response_model=MemoryGraphResponse)
async def get_memory_graph(
    client: Client,
    session_id: str = Query(..., description="Session ID"),
) -> MemoryGraphResponse:
    """Get memory graph for visualization."""
    try:
        graph = await client.get_graph(session_id=session_id)
        nodes = [
            GraphNodeResponse(id=n.id, labels=n.labels, properties=n.properties)
            for n in graph.nodes
        ]
        relationships = [
            GraphRelationshipResponse(
                id=r.id, type=r.type, from_node=r.from_node,
                to_node=r.to_node, properties=r.properties,
            )
            for r in graph.relationships
        ]
        return MemoryGraphResponse(nodes=nodes, relationships=relationships)
    except Exception:
        logger.exception("Error loading memory graph")
        raise HTTPException(status_code=500, detail="Failed to load memory graph")


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    client: Client,
    session_id: str = Query(..., description="Session ID"),
    category: str | None = Query(None, description="Filter by category"),
) -> PreferencesResponse:
    """Get learned user preferences."""
    try:
        prefs = await client.long_term.search_preferences(
            query=category or "",
            category=category,
            limit=20,
        )
        items = [
            PreferenceItem(
                category=p.category,
                preference=p.preference,
                context=p.context,
                confidence=p.confidence,
            )
            for p in prefs
        ]
        return PreferencesResponse(preferences=items)
    except Exception:
        logger.exception("Error loading preferences")
        raise HTTPException(status_code=500, detail="Failed to load preferences")
