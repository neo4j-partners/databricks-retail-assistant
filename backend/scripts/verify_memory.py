"""Standalone verification of the Neo4jAgentMemory LangChain integration.

Proves that save_context, load_memory_variables, and Neo4jMemoryRetriever
all work against a live Neo4j instance before building anything on top.

Usage:
    python -m backend.scripts.verify_memory
"""

from __future__ import annotations

import asyncio
import sys

from backend.config import get_memory_settings

from neo4j_agent_memory import MemoryClient
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory, Neo4jMemoryRetriever


TEST_SESSION_ID = "verify-memory-test"


async def run_verification() -> bool:
    memory_settings = get_memory_settings()
    client = MemoryClient(memory_settings)
    passed = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        status = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{status}] {name}{suffix}")
        if ok:
            passed += 1
        else:
            failed += 1

    print("[STEP 1] Connect to Neo4j")
    try:
        await client.connect()
        check("MemoryClient.connect()", client.is_connected)
    except Exception as e:
        check("MemoryClient.connect()", False, str(e))
        return False

    try:
        # --- Save context ---
        print("\n[STEP 2] Save context via Neo4jAgentMemory")
        memory = Neo4jAgentMemory(
            memory_client=client,
            session_id=TEST_SESSION_ID,
            include_short_term=True,
            include_long_term=True,
            include_reasoning=True,
        )

        await memory._save_context_async(
            {"input": "I like Nike running shoes"},
            {"output": "Great choice! Nike has excellent running shoes."},
        )
        check("save_context (user + assistant)", True)

        # --- Load memory variables ---
        print("\n[STEP 3] Load memory variables")
        result = await memory._load_memory_variables_async({"input": "running shoes"})

        expected_keys = {"history", "context", "preferences", "similar_tasks"}
        actual_keys = set(result.keys())
        check(
            "load_memory_variables returns expected keys",
            expected_keys == actual_keys,
            f"got {sorted(actual_keys)}",
        )

        history = result.get("history", "")
        has_saved_message = "Nike" in history or "running shoes" in history.lower()
        check(
            "history contains saved conversation",
            has_saved_message,
            f"history length={len(history)} chars",
        )

        check(
            "context is a string",
            isinstance(result.get("context"), str),
            f"type={type(result.get('context')).__name__}",
        )

        check(
            "preferences is a list",
            isinstance(result.get("preferences"), list),
            f"count={len(result.get('preferences', []))}",
        )

        check(
            "similar_tasks is a string",
            isinstance(result.get("similar_tasks"), str),
            f"length={len(result.get('similar_tasks', ''))}",
        )

        # --- Neo4jMemoryRetriever ---
        print("\n[STEP 4] Neo4jMemoryRetriever")
        retriever = Neo4jMemoryRetriever(
            memory_client=client,
            k=5,
            threshold=0.5,
        )

        docs = await retriever._get_relevant_documents_async("Nike shoes")
        check(
            "retriever returns documents",
            len(docs) > 0,
            f"count={len(docs)}",
        )

        if docs:
            first = docs[0]
            check(
                "document has page_content",
                bool(first.page_content),
                f"content={first.page_content[:80]}",
            )
            check(
                "document has type metadata",
                "type" in first.metadata,
                f"type={first.metadata.get('type')}",
            )

        # --- get_graph ---
        print("\n[STEP 5] MemoryClient.get_graph()")
        graph = await client.get_graph(session_id=TEST_SESSION_ID)
        check(
            "get_graph returns MemoryGraph",
            hasattr(graph, "nodes") and hasattr(graph, "relationships"),
            f"nodes={len(graph.nodes)}, relationships={len(graph.relationships)}",
        )

        # --- Cleanup test data ---
        print("\n[STEP 6] Cleanup test session")
        await client.short_term.clear_session(TEST_SESSION_ID)
        check("clear_session", True)

    except Exception as e:
        print(f"\n  UNEXPECTED ERROR: {type(e).__name__}: {e}")
        failed += 1
    finally:
        await client.close()
        print(f"\n  Disconnected from Neo4j")

    print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


def main() -> None:
    ok = asyncio.run(run_verification())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
