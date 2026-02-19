"""Bare-bones LangGraph agent with a single echo tool.

This is the Step 2 prototype from PROTOTYPE.md. It validates that
create_react_agent + ChatAgent deploys to Databricks Model Serving
without any external dependencies (no Neo4j, no OpenAI, no secrets).

The echo tool exists solely to prove the agent can invoke tools and
return results through the serving endpoint.
"""

from langchain_core.tools import tool


@tool
def echo(message: str) -> str:
    """Echo back the user's message. Use this tool to repeat what the user said."""
    return f"Echo: {message}"


SYSTEM_PROMPT = (
    "You are a test agent for validating Databricks deployment. "
    "You have one tool called 'echo' that repeats messages back. "
    "When the user sends a message, use the echo tool to repeat it, "
    "then confirm it worked."
)


def create_prototype_agent(llm=None):
    """Create a minimal LangGraph ReAct agent with one echo tool.

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
        tools=[echo],
        prompt=SYSTEM_PROMPT,
    )
