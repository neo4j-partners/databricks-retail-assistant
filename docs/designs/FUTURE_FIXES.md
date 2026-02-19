# Future Fixes

Issues identified during the embedding implementation review that are outside the scope of the current changes. These are pre-existing patterns that should be improved.

## dbx_agent/memory_tool.py

- **Private method access**: `search_memory` calls `retriever._get_relevant_documents_async()` which is a private API. Should use the public `retriever.ainvoke()` or `retriever.aget_relevant_documents()` if available in the LangChain version.
- **No error handling**: None of the three tools (`remember_message`, `recall_memory`, `search_memory`) have try/except around client calls. If Neo4j is down or the session is invalid, exceptions propagate to the agent with no useful message. The `product_search.py` tools handle this well and should be used as the pattern.

## dbx_agent/serving.py

- **Missing `from __future__ import annotations`**: Present in `product_search.py` but not here. Causes inconsistency with type hint evaluation.
- **Missing type hints on `predict()`**: The method signature lacks parameter types. Should match the `ChatAgent` base class signature.

## dbx_agent/config.py

- **Missing `from __future__ import annotations`**: Inconsistent with other files in the package.
- **Fragile enum parsing**: `RunMode.DELETE if run_mode_str == "delete"` — the `.lower()` call is on line 102 but the pattern is brittle. Consider using a helper or `RunMode(value)` with error handling.

## backend/scripts/load_products.py

- **Missing `from __future__ import annotations`**: Inconsistent with `backend/config.py` which has it.
- **Broad exception handling**: The `except Exception` blocks in `_create_vector_index` and `_generate_embeddings` catch everything without distinguishing recoverable from fatal errors.

## backend/config.py

- **Missing return type on `get_memory_settings()`**: Should be `-> MemorySettings`.
- **Raw dict for Neo4j config**: Lines 59-63 pass a raw dict instead of constructing `Neo4jConfig` directly, bypassing Pydantic validation at construction time.
