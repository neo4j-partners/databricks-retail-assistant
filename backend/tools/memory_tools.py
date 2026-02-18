"""Memory retrieval tools for the LangGraph retail agent.

Wraps Neo4jMemoryRetriever to allow the agent to search conversation history,
entities, and preferences stored in Neo4j.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from neo4j_agent_memory import MemoryClient
from neo4j_agent_memory.integrations.langchain import Neo4jMemoryRetriever

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------


class MemorySearchInput(BaseModel):
    """Input for searching agent memory."""

    query: str = Field(description="Search query for finding relevant memories")
    search_type: Literal["all", "messages", "entities", "preferences"] = Field(
        default="all",
        description="Type of memory to search: all, messages, entities, or preferences",
    )
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results")


# ---------------------------------------------------------------------------
# Tool Factories
# ---------------------------------------------------------------------------


def create_memory_tools(client: MemoryClient) -> list[BaseTool]:
    """Create memory search tools bound to the given MemoryClient."""

    @tool(args_schema=MemorySearchInput)
    async def search_memory(
        query: str,
        search_type: Literal["all", "messages", "entities", "preferences"] = "all",
        limit: int = 5,
    ) -> str:
        """Search the memory store for relevant past conversations, extracted entities, and learned preferences. Use this to recall what the customer has said before or what preferences they have expressed."""
        retriever = Neo4jMemoryRetriever(
            memory_client=client,
            k=limit,
            threshold=0.5,
        )

        docs = await retriever._get_relevant_documents_async(query)

        # Filter by search type if specified
        if search_type != "all":
            type_map = {
                "messages": "message",
                "entities": "entity",
                "preferences": "preference",
            }
            target_type = type_map.get(search_type, search_type)
            docs = [d for d in docs if d.metadata.get("type") == target_type]

        results = []
        for doc in docs[:limit]:
            results.append({
                "content": doc.page_content,
                "type": doc.metadata.get("type", "unknown"),
                "similarity": doc.metadata.get("similarity", 0.0),
            })

        return json.dumps({
            "query": query,
            "search_type": search_type,
            "results": results,
            "count": len(results),
        })

    return [search_memory]
