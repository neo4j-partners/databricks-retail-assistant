"""Memory tools using neo4j-agent-memory.

Provides short-term store/recall and semantic search over memory:
- remember_message: store a message in short-term memory
- recall_memory: retrieve full conversation history
- search_memory: semantic similarity search via Neo4jMemoryRetriever
"""

import json

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


@tool
async def search_memory(
    query: str,
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Search memory for relevant past conversations and facts using semantic similarity.

    Use this tool when the user asks about something specific from past conversations,
    or when you need to find relevant context without retrieving the full history.
    """
    from neo4j_agent_memory.integrations.langchain import Neo4jMemoryRetriever

    client = runtime.context.client
    retriever = Neo4jMemoryRetriever(
        memory_client=client,
        k=5,
        threshold=0.5,
    )

    docs = await retriever._get_relevant_documents_async(query)

    results = []
    for doc in docs[:5]:
        results.append({
            "content": doc.page_content,
            "type": doc.metadata.get("type", "unknown"),
            "similarity": doc.metadata.get("similarity", 0.0),
        })

    return json.dumps({
        "query": query,
        "results": results,
        "count": len(results),
    })


# Flat tool list for import by agent.py
MEMORY_TOOLS = [remember_message, recall_memory, search_memory]
