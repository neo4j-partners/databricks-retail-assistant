"""Memory tools using neo4j-agent-memory.

Provides short-term store/recall, semantic search, and long-term preferences:
- remember_message: store a message in short-term memory (with entity extraction)
- recall_memory: retrieve full conversation history
- search_memory: semantic similarity search via short_term.search_messages
- track_preference: store a user preference in long-term memory
- get_user_profile: retrieve all stored preferences for the current user
"""

import json
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from memory_helpers import get_user_preferences, store_user_preference
from retail_context import RetailContext

logger = logging.getLogger(__name__)


@tool
async def remember_message(
    content: str,
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Store a message in short-term memory and return the conversation history.

    Use this tool when the user asks you to remember something, or when you
    want to save important information from the conversation.
    """
    client = runtime.context.client
    session_id = runtime.context.session_id or "default"

    await client.short_term.add_message(
        session_id,
        "user",
        content,
        extract_entities=True,
        generate_embedding=True,
    )

    # Retrieve the conversation to confirm storage
    conversation = await client.short_term.get_conversation(session_id)
    messages = conversation.messages

    if not messages:
        return "Message stored, but no conversation history found."

    lines = [f"Stored message. Conversation has {len(messages)} message(s):"]
    for msg in messages:
        lines.append(f"  [{msg.role}] {msg.content}")
    return "\n".join(lines)


@tool
async def recall_memory(
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Retrieve the conversation history from short-term memory.

    Use this tool when the user asks what you remember, or to check
    what has been stored in memory.
    """
    client = runtime.context.client
    session_id = runtime.context.session_id or "default"

    conversation = await client.short_term.get_conversation(session_id)
    messages = conversation.messages

    if not messages:
        return "No messages found in memory."

    lines = [f"Found {len(messages)} message(s) in memory:"]
    for msg in messages:
        lines.append(f"  [{msg.role}] {msg.content}")
    return "\n".join(lines)


@tool
async def search_memory(
    query: str,
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Search memory for relevant past conversations and facts using semantic similarity.

    Use this tool when the user asks about something specific from past conversations,
    or when you need to find relevant context without retrieving the full history.
    """
    client = runtime.context.client
    messages = await client.short_term.search_messages(query, limit=5, threshold=0.5)

    results = []
    for msg in messages:
        results.append({
            "content": msg.content,
            "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
            "similarity": msg.metadata.get("similarity", 0.0),
        })

    return json.dumps({
        "query": query,
        "results": results,
        "count": len(results),
    })


@tool
async def track_preference(
    preference_type: str,
    preference_value: str,
    context: str | None = None,
    *,
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Store a user preference in long-term memory for future personalization.

    Use this tool when the user expresses a preference such as a preferred
    brand, category, size, budget range, or activity type. Preferences persist
    across sessions and are used to personalize future recommendations.

    Args:
        preference_type: Category of preference (e.g. 'brand', 'category',
            'size', 'price_range', 'activity', 'material', 'style').
        preference_value: The preference itself (e.g. 'trail running',
            'waterproof', 'Nike', 'under $200', 'size 11').
        context: Optional context for when/where the preference applies.
    """
    client = runtime.context.client
    user_id = runtime.context.user_id

    if not user_id:
        return json.dumps({
            "error": "Cannot store preferences without a user_id. "
            "Preferences require a user identity to persist across sessions."
        })

    try:
        preference = await client.long_term.add_preference(
            category=preference_type,
            preference=f"{preference_type}: {preference_value}",
            context=context,
            generate_embedding=True,
        )
        return json.dumps({
            "stored": True,
            "preference_type": preference_type,
            "preference_value": preference_value,
            "user_id": user_id,
        })
    except Exception as e:
        logger.warning("Failed to store preference: %s", e)
        return json.dumps({"error": "Failed to store preference", "detail": str(e)})


@tool
async def get_user_profile(
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Retrieve the current user's stored preferences from long-term memory.

    Use this tool at the start of a session to understand the user's
    preferences, or mid-conversation when you need to check what you
    already know about them. Returns all stored preferences including
    brand, category, size, budget, and activity preferences.
    """
    client = runtime.context.client
    user_id = runtime.context.user_id

    if not user_id:
        return json.dumps({
            "preferences": [],
            "note": "No user_id provided — cannot retrieve long-term preferences.",
        })

    try:
        # Search all preferences (broad query to get everything)
        preferences = await client.long_term.search_preferences(
            query="user preferences",
            limit=20,
            threshold=0.0,
        )

        results = []
        for pref in preferences:
            results.append({
                "category": pref.category,
                "preference": pref.preference,
                "context": pref.context,
                "confidence": pref.confidence,
            })

        return json.dumps({
            "user_id": user_id,
            "preferences": results,
            "count": len(results),
        })
    except Exception as e:
        logger.warning("Failed to retrieve user profile: %s", e)
        return json.dumps({"error": "Failed to retrieve preferences", "detail": str(e)})


# Flat tool list for import by react_agent.py
MEMORY_TOOLS = [remember_message, recall_memory, search_memory, track_preference, get_user_profile]
