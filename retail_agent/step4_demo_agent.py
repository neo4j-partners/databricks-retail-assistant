"""Verify the deployed agent endpoint on Databricks.

Checks the endpoint exists, sends sample queries from CONFIG, and prints responses.
Uses raw REST calls (like aircraft_analyst) instead of the SDK's query() method,
which can have issues deserializing ChatAgent responses.

Runs on a Databricks cluster or as a Databricks Job.
"""

import sys
from uuid import uuid4

import requests

from retail_agent.src.deploy_config import CONFIG
from retail_agent.src.endpoint_client import (
    ensure_endpoint_ready,
    extract_content,
    run_exercise,
    send_message,
)


def _run_memory_exercise(endpoint_url: str, headers: dict) -> tuple[int, int]:
    """Exercise memory tools with a multi-turn conversation sharing a session.

    Creates a unique session_id and sends a scripted conversation that tests:
    1. Storing facts via remember_message
    2. Recalling the full history via recall_memory
    3. Searching memory semantically via search_memory
    4. Using remembered context for recommendations
    """
    session_id = f"check-memory-{uuid4().hex[:8]}"
    custom_inputs = {"session_id": session_id}

    turns = [
        (
            "Remember that my name is Alex and I prefer trail running shoes.",
            "Store preferences",
            ["alex", "trail"],
        ),
        (
            "Remember that I wear size 11 and my budget is around $150.",
            "Store sizing/budget",
            ["size", "11"],
        ),
        (
            "What do you remember about me?",
            "Full recall",
            ["alex", "trail", "size", "11"],
        ),
        (
            "Search your memory for anything about my shoe preferences.",
            "Semantic memory search",
            ["trail", "running"],
        ),
        (
            "Based on what you know about me, recommend a product.",
            "Memory-based recommendation",
            ["trail", "running"],
        ),
    ]

    print(f"  Session ID: {session_id}")
    print(f"  Turns: {len(turns)}")
    return run_exercise(
        endpoint_url, headers, turns, custom_inputs,
        response_limit=300, accumulate_history=True,
    )


def check_endpoint() -> int:
    """Run basic checks against the deployed endpoint."""
    try:
        endpoint_url, headers = ensure_endpoint_ready()
    except (RuntimeError, ValueError) as e:
        print(f"  Error: {e}")
        return 1

    print(f"  LLM endpoint: {CONFIG.llm_endpoint}")
    print(f"  Embedding model: {CONFIG.embedding_model}")

    # Run diagnostics check
    print()
    print("Running diagnostics:")
    print("-" * 40)
    try:
        text = send_message(
            endpoint_url, headers,
            "Run agent_diagnostics and return the raw JSON output only, no commentary.",
        )
        if text:
            print(text)
        else:
            print("(no response text)")
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

    # Send sample queries — each tagged with the concept it demonstrates
    query_concepts = {
        "Echo hello world": "Basic connectivity",
        "Remember that my favorite color is blue": "Memory storage",
        "What do you remember about me?": "Memory recall",
        "Search for running shoes under $200": "Product search (Neo4j)",
        "Get details for product 'nike-pegasus-40'": "Product lookup (Neo4j)",
        "What products are related to 'brooks-ghost-16'?": "Graph traversal (Neo4j)",
    }

    print()
    print("Running sample queries:")
    print("=" * 50)

    for i, query in enumerate(CONFIG.sample_queries, 1):
        concept = query_concepts.get(query, "General")
        print(f"\n#### [{i}/{len(CONFIG.sample_queries)}] {concept}")
        print(f"Q: {query}")
        try:
            text = send_message(endpoint_url, headers, query)
            if text:
                print(f"A: {text[:500]}")
            else:
                print("A: (no response text)")
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
        print(f"#### end {concept}")

    # Memory exercise — multi-turn session with shared session_id
    print()
    print("Running memory exercise:")
    print("-" * 40)
    mem_passed, mem_failed = _run_memory_exercise(endpoint_url, headers)
    print(f"\nMemory exercise: {mem_passed} passed, {mem_failed} failed")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(check_endpoint())
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    check_endpoint()
