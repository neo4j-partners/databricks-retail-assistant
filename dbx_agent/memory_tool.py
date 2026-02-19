"""Prototype memory tool using neo4j-agent-memory short-term memory.

This is the Step 3 prototype from PROTOTYPE.md. It validates:
1. The neo4j-agent-memory wheel works in the serving container
2. ToolRuntime[RetailContext] injection works in practice
3. The asyncio.run() bridge works with async-only tools

The tool stores and retrieves messages via MemoryClient.short_term —
the simplest meaningful interaction that exercises the Neo4j connection,
the async driver, and the core MemoryClient API without requiring
embeddings or entity extraction.
"""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from context import RetailContext


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

    # Store the message (no embeddings or entity extraction for prototype)
    await client.short_term.add_message(
        session_id,
        "user",
        content,
        extract_entities=False,
        generate_embedding=False,
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


# Flat tool list for import by agent.py
MEMORY_TOOLS = [remember_message, recall_memory]
