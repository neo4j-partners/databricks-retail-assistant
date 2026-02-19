"""Diagnostics tool for verifying the deployed agent environment.

Reports library versions, client status, and capability flags so
check_endpoint.py can confirm the correct code is deployed.
"""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from context import RetailContext


@tool
def agent_diagnostics(
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Return diagnostic information about the agent environment.

    Use this tool when asked about versions, status, or diagnostics.
    """
    info = {}

    # Library version
    try:
        import neo4j_agent_memory

        info["neo4j_agent_memory_version"] = getattr(
            neo4j_agent_memory, "__version__", "unknown"
        )
    except ImportError:
        info["neo4j_agent_memory_version"] = "not installed"

    # Client status
    client = runtime.context.client
    info["client_initialized"] = client is not None
    if client is not None:
        info["has_graph"] = getattr(client, "_client", None) is not None
        info["has_embedder"] = getattr(client, "_embedder", None) is not None
        info["has_short_term"] = getattr(client, "short_term", None) is not None
        info["has_long_term"] = getattr(client, "long_term", None) is not None

    # Session info
    info["session_id"] = runtime.context.session_id

    # Serving module version check
    try:
        import importlib
        import inspect

        serving = importlib.import_module("serving")
        source = inspect.getsource(serving.PrototypeAgent.predict)
        if "run_coroutine_threadsafe" in source:
            info["async_bridge"] = "persistent_loop"
        elif "asyncio.run" in source:
            info["async_bridge"] = "asyncio_run"
        else:
            info["async_bridge"] = "unknown"
    except Exception:
        info["async_bridge"] = "check_failed"

    import json

    return json.dumps(info, indent=2)


DIAGNOSTICS_TOOLS = [agent_diagnostics]
