"""Shared context for retail agent tools.

RetailContext for dependency injection via ToolRuntime.
This dataclass is injected into tools via ToolRuntime[RetailContext] at
invocation time. The MemoryClient and session_id are constructed by whoever
invokes the agent — locally or via the Databricks serving adapter.
"""

from dataclasses import dataclass

from neo4j_agent_memory import MemoryClient


@dataclass
class RetailContext:
    """All external dependencies for retail agent tools.

    Injected by LangGraph at invocation time via ToolRuntime.
    Constructed by the Databricks Model Serving adapter (serving_adapter.py).
    """

    client: MemoryClient
    session_id: str | None = None
    user_id: str | None = None
