"""Shared helpers for user-scoped long-term memory operations.

The neo4j-agent-memory library stores preferences globally — it has no
built-in user_id scoping. These helpers enforce user isolation by:
- Attaching user_id in metadata when storing preferences
- Filtering by user_id in metadata when retrieving preferences
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j_agent_memory import MemoryClient

logger = logging.getLogger(__name__)


async def store_user_preference(
    client: MemoryClient,
    user_id: str,
    category: str,
    preference: str,
    context: str | None = None,
) -> Any:
    """Store a preference scoped to a specific user via metadata.

    Returns the Preference object from the memory client.
    """
    return await client.long_term.add_preference(
        category=category,
        preference=preference,
        context=context,
        generate_embedding=True,
        metadata={"user_id": user_id},
    )


async def get_user_preferences(
    client: MemoryClient,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """Retrieve all preferences for a specific user.

    Fetches preferences broadly then filters client-side by user_id
    in metadata, since the library has no native user scoping.

    Returns a list of dicts with category, preference, context, confidence.
    """
    try:
        all_preferences = await client.long_term.search_preferences(
            query="user preferences",
            limit=limit,
            threshold=0.0,
        )
    except Exception as e:
        logger.warning("Failed to retrieve preferences for user %s: %s", user_id, e)
        return []

    results = []
    for pref in all_preferences:
        if pref.metadata.get("user_id") != user_id:
            continue
        results.append({
            "category": pref.category,
            "preference": pref.preference,
            "context": pref.context,
            "confidence": pref.confidence,
        })
    return results
