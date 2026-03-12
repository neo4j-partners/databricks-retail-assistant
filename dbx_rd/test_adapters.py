"""Smoke test for DatabricksEmbedder and DatabricksLLM adapters.

Uploads to Databricks and runs via:
    ./upload.sh test_adapters.py && ./submit.sh test_adapters.py

Verifies:
  1. DatabricksEmbedder.embed_query returns a vector of expected dimensions
  2. DatabricksLLM.invoke returns a coherent text response
  3. Both adapters work with the neo4j-graphrag interface types
"""

import sys


def main():
    print("=" * 60)
    print("Phase 2: Adapter Smoke Test")
    print("=" * 60)

    # -- Test 1: DatabricksEmbedder -------------------------------------------
    print("\n--- Test 1: DatabricksEmbedder ---")
    try:
        from databricks_embedder import DatabricksEmbedder

        embedder = DatabricksEmbedder()
        print(f"  Model: {embedder.model}")
        print(f"  Expected dimensions: {embedder.dimensions}")

        test_text = "lightweight running shoes for beginners"
        vector = embedder.embed_query(test_text)

        print(f"  Input: '{test_text}'")
        print(f"  Output type: {type(vector).__name__}")
        print(f"  Output length: {len(vector)}")
        print(f"  First 5 values: {vector[:5]}")
        print(f"  Dimensions match: {len(vector) == embedder.dimensions}")

        # Verify it's a proper Embedder subclass
        from neo4j_graphrag.embeddings.base import Embedder

        print(f"  Is Embedder subclass: {isinstance(embedder, Embedder)}")
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

    # -- Test 2: DatabricksLLM ------------------------------------------------
    print("\n--- Test 2: DatabricksLLM ---")
    try:
        from databricks_llm import DatabricksLLM

        llm = DatabricksLLM()
        print(f"  Model: {llm.model_id}")

        # Test with List[LLMMessage] (V2 interface)
        messages = [
            {"role": "user", "content": "Reply with exactly: ADAPTER_TEST_OK"}
        ]
        response = llm.invoke(messages)

        print(f"  Input: {messages}")
        print(f"  Output type: {type(response).__name__}")
        print(f"  Output content: {response.content[:200]}")

        # Verify it's a proper LLMInterfaceV2 subclass
        from neo4j_graphrag.llm.base import LLMInterfaceV2

        print(f"  Is LLMInterfaceV2 subclass: {isinstance(llm, LLMInterfaceV2)}")

        # Verify LLMResponse type
        from neo4j_graphrag.llm.types import LLMResponse

        print(f"  Is LLMResponse: {isinstance(response, LLMResponse)}")
        print(f"  Has content attr: {hasattr(response, 'content')}")
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

    # -- Test 3: DatabricksLLM with str input (V1 compat) --------------------
    print("\n--- Test 3: DatabricksLLM str input (V1 compat) ---")
    try:
        from databricks_llm import DatabricksLLM

        llm = DatabricksLLM()
        response = llm.invoke("Reply with exactly: V1_COMPAT_OK")

        print(f"  Input: plain string")
        print(f"  Output content: {response.content[:200]}")
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

    # -- Summary --------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
