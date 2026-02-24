"""LangGraph agent with echo tool and neo4j-agent-memory integration.

Step 3 prototype from PROTOTYPE.md. Builds on Step 2 by adding:
- ToolRuntime[RetailContext] injection via context_schema
- Async memory tools backed by neo4j-agent-memory short-term memory
- The echo tool is retained for baseline validation

The agent uses create_react_agent with context_schema=RetailContext so
that ToolRuntime[RetailContext] parameters are injected automatically.
"""

from langchain_core.tools import tool

from deploy_config import CONFIG
from retail_context import RetailContext
from commerce_tools import COMMERCE_TOOLS
from diagnostics_tool import DIAGNOSTICS_TOOLS
from knowledge_tools import KNOWLEDGE_TOOLS
from memory_tools import MEMORY_TOOLS
from product_tools import PRODUCT_SEARCH_TOOLS
from reasoning_tools import REASONING_TOOLS


@tool
def echo(message: str) -> str:
    """Echo back the user's message. Use this tool to repeat what the user said."""
    return f"Echo: {message}"


SYSTEM_PROMPT = (
    "You are a retail product assistant with access to a Neo4j knowledge graph, "
    "long-term user memory, and reasoning trace capabilities. You can search "
    "products, diagnose issues, track user preferences, learn from past "
    "interactions, and provide personalized recommendations.\n\n"

    "SESSION START:\n"
    "- If a user_id is present, call get_user_profile at the start of the "
    "session to load stored preferences. Use this context to personalize all "
    "subsequent responses.\n\n"

    "TOOL SELECTION GUIDE:\n"
    "- For browsing, pricing, and catalog queries (e.g. 'show me running shoes "
    "under $150'), use search_products, get_product_details, get_related_products.\n"
    "- For support questions, troubleshooting, 'how do I fix', and product issue "
    "queries (e.g. 'my shoes feel flat', 'outsole peeling'), use knowledge_search "
    "or hybrid_knowledge_search.\n"
    "- When the query includes specific brand names or technical terms alongside a "
    "general question, prefer hybrid_knowledge_search over knowledge_search.\n"
    "- To find known issues and solutions for a specific product, use "
    "diagnose_product_issue with the product ID.\n\n"

    "PREFERENCES:\n"
    "- When the user expresses a preference (brand, category, size, budget, "
    "activity type, material, style), call track_preference to save it for "
    "future sessions.\n"
    "- Examples: 'I prefer Nike' -> track brand preference. 'My budget is "
    "under $200' -> track price_range preference. 'I need waterproof' -> "
    "track material preference.\n\n"

    "PERSONALIZED RECOMMENDATIONS:\n"
    "- When a user with stored preferences asks for recommendations, prefer "
    "recommend_for_user over raw product search. It combines their preference "
    "profile with knowledge graph traversal for better results.\n"
    "- If the user has no stored preferences, recommend_for_user falls back to "
    "standard knowledge search.\n\n"

    "REASONING TRACES:\n"
    "- When starting a multi-step task (product comparison, troubleshooting "
    "workflow, purchase recommendation), first call recall_past_reasoning to "
    "check if a similar task was handled before.\n"
    "- After completing a multi-step task, call record_reasoning_trace to log "
    "the approach, steps taken, and outcome for future learning.\n\n"

    "MEMORY:\n"
    "- Short-term memory (remember_message, recall_memory, search_memory) is "
    "for the current conversation session.\n"
    "- Long-term memory (track_preference, get_user_profile) persists across "
    "sessions and is tied to the user, not the session.\n"
    "- Reasoning traces (record_reasoning_trace, recall_past_reasoning) persist "
    "across sessions and help the agent learn from experience."
)

ALL_TOOLS = (
    [echo]
    + MEMORY_TOOLS
    + PRODUCT_SEARCH_TOOLS
    + KNOWLEDGE_TOOLS
    + REASONING_TOOLS
    + COMMERCE_TOOLS
    + DIAGNOSTICS_TOOLS
)


def create_prototype_agent(llm=None):
    """Create a LangGraph ReAct agent with echo and memory tools.

    Args:
        llm: Optional LLM override. Defaults to ChatDatabricks with
             databricks-meta-llama-3-3-70b-instruct.
    """
    from langgraph.prebuilt import create_react_agent

    if llm is None:
        from databricks_langchain import ChatDatabricks

        llm = ChatDatabricks(endpoint=CONFIG.llm_endpoint)

    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
        context_schema=RetailContext,
    )
