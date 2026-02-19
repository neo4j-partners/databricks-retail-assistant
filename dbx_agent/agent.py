"""LangGraph agent with echo tool and neo4j-agent-memory integration.

Step 3 prototype from PROTOTYPE.md. Builds on Step 2 by adding:
- ToolRuntime[RetailContext] injection via context_schema
- Async memory tools backed by neo4j-agent-memory short-term memory
- The echo tool is retained for baseline validation

The agent uses create_react_agent with context_schema=RetailContext so
that ToolRuntime[RetailContext] parameters are injected automatically.
"""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from context import RetailContext
from diagnostics_tool import DIAGNOSTICS_TOOLS
from memory_tool import MEMORY_TOOLS
from product_search import PRODUCT_SEARCH_TOOLS


@tool
def echo(message: str) -> str:
    """Echo back the user's message. Use this tool to repeat what the user said."""
    return f"Echo: {message}"


SYSTEM_PROMPT = (
    "You are a retail product assistant with access to a Neo4j knowledge graph. "
    "You can search products, get product details, find related products, "
    "and manage conversation memory.\n\n"
    "Use your tools to help customers find products, learn about items, "
    "and discover related products. When the user asks you to remember "
    "something, use the remember_message tool. When the user asks what "
    "you remember, use the recall_memory tool to retrieve the full conversation "
    "history. When the user asks about something specific from past conversations, "
    "use the search_memory tool for semantic similarity search."
)

ALL_TOOLS = [echo] + MEMORY_TOOLS + PRODUCT_SEARCH_TOOLS + DIAGNOSTICS_TOOLS


def create_prototype_agent(llm=None):
    """Create a LangGraph ReAct agent with echo and memory tools.

    Args:
        llm: Optional LLM override. Defaults to ChatDatabricks with
             databricks-meta-llama-3-3-70b-instruct.
    """
    from langgraph.prebuilt import create_react_agent

    if llm is None:
        from databricks_langchain import ChatDatabricks

        llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
        context_schema=RetailContext,
    )
