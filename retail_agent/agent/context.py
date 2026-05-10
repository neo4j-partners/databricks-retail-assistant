"""Shared context for retail agent tools.

RetailContext for dependency injection via ToolRuntime.
This dataclass is injected into tools via ToolRuntime[RetailContext] at
invocation time. The MemoryClient and session_id are constructed by whoever
invokes the agent — locally or via the Databricks serving adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j_agent_memory import MemoryClient


@dataclass
class RetailContext:
    """All external dependencies for retail agent tools.

    Injected by LangGraph at invocation time via ToolRuntime.
    Constructed by the Databricks Model Serving adapter.
    """

    client: MemoryClient
    session_id: str | None = None
    user_id: str | None = None
