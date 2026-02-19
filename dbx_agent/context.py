"""Shared context for retail agent tools.

Prototype version of the RetailContext from LANGCHAIN_AGENT.md Section 1.
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
    Local scripts and Databricks Model Serving each construct
    their own RetailContext — tool code is identical in both.
    """

    client: MemoryClient
    session_id: str | None = None
