"""Tool factory for the LangGraph retail agent.

Provides a single entry point to create all agent tools with their
MemoryClient dependency injected via closure — no global state.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from neo4j_agent_memory import MemoryClient

from backend.tools.cart import create_cart_tools
from backend.tools.inventory import create_inventory_tools
from backend.tools.memory_tools import create_memory_tools
from backend.tools.product_search import create_product_search_tools
from backend.tools.recommendations import create_recommendation_tools

__all__ = ["create_tools"]


def create_tools(client: MemoryClient) -> list[BaseTool]:
    """Create all agent tools bound to the given MemoryClient.

    Returns a flat list of LangChain tool objects ready to be passed
    to ``create_react_agent``.
    """
    return [
        *create_product_search_tools(client),
        *create_recommendation_tools(client),
        *create_inventory_tools(client),
        *create_cart_tools(client),
        *create_memory_tools(client),
    ]
