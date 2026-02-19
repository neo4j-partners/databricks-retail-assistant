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
from memory_tool import MEMORY_TOOLS


@tool
def echo(message: str) -> str:
    """Echo back the user's message. Use this tool to repeat what the user said."""
    return f"Echo: {message}"


SYSTEM_PROMPT = (
    "You are a test agent for validating Databricks deployment with Neo4j memory. "
    "You have three tools:\n"
    "- 'echo': repeats messages back (for basic validation)\n"
    "- 'remember_message': stores information in Neo4j short-term memory\n"
    "- 'recall_memory': retrieves conversation history from memory\n\n"
    "When the user asks you to remember something, use the remember_message tool. "
    "When the user asks what you remember, use the recall_memory tool. "
    "For other messages, use the echo tool."
)

ALL_TOOLS = [echo] + MEMORY_TOOLS


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
