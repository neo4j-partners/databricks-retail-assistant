# Proposal: Expand Retail Agent to GraphRAG-Powered Agentic Commerce

## Problem Statement

The retail agent today operates as a product search assistant. It can find products by vector similarity, look up details, traverse basic graph relationships (category, brand, attribute), and maintain short-term conversation memory. These are useful capabilities, but they leave two significant gaps.

First, the agent cannot answer questions that require knowledge beyond the product catalog. The GraphRAG layer already exists in Neo4j — Chunk nodes with embeddings, extracted Feature/Symptom/Solution entities, and entity-to-product links — but the agent has no tools to reach it. A customer asking "my running shoes feel flat after 300 miles, what should I do?" gets a product search result instead of a grounded answer that traverses from symptom to solution to related products across the knowledge graph. The retriever patterns demonstrated in `step5_demo_retrievers.py` (VectorCypherRetriever, HybridCypherRetriever, Text2CypherRetriever) prove the value of entity-aware retrieval, but none of them are wired into the live agent.

Second, the agent has no long-term learning. Every session starts from zero. There is no reasoning memory, no preference tracking, no ability to recall that a customer prefers trail shoes over road shoes or that a particular negotiation approach worked last quarter. The agent cannot accumulate operational intelligence, which is the foundation of agentic commerce.

## Proposed Solution

Two phases, each delivering a usable agent upgrade.

**Phase 1** brings the GraphRAG retrieval patterns from the demo directly into the agent's tool set. The agent gains the ability to answer support questions, diagnose product issues, and surface cross-product insights by traversing the entity graph — all within the existing architecture.

**Phase 2** adds the three-layer memory architecture and agentic commerce capabilities. The agent tracks user preferences across sessions, records reasoning traces, and uses past experience to improve future interactions. This transforms the agent from a stateless assistant into a learning commerce agent.

---

## Phase 1: GraphRAG Tools in the Live Agent — IMPLEMENTED

### What Changes

Three new tools added to `src/`, registered in `react_agent.py` alongside the existing product and memory tools.

### Requirements

1. **`knowledge_search` tool** — Takes a natural language query, runs VectorCypherRetriever against the `chunk_embedding` index, traverses MENTIONS_FEATURE / REPORTS_SYMPTOM / PROVIDES_SOLUTION relationships from matched chunks, and returns the chunk text plus extracted entities and related products. This is the VECTOR_CYPHER_QUERY pattern from `step5_demo_retrievers.py` adapted as an agent tool. Uses `client.graph.execute_read()` for the vector call and Cypher traversal (same access pattern as existing product tools), and `client._embedder.embed()` for query embedding (same pattern as `search_products`).

2. **`hybrid_knowledge_search` tool** — Takes a query, runs against both the `chunk_embedding` vector index and `chunkText` fulltext index, blends results, then traverses entity relationships. Handles queries where exact terminology matters (brand names, specific part names) alongside semantic similarity. This is the HYBRID_CYPHER_QUERY pattern from the demo.

3. **`diagnose_product_issue` tool** — Takes a product ID and optional symptom description, traverses the graph from Product through HAS_SYMPTOM and HAS_SOLUTION relationships, and returns known symptoms and their solutions. When a symptom description is provided, uses embedding similarity to rank the most relevant symptoms. This tool does not exist in the demo — it is a new composition of the entity graph for direct product diagnostics.

4. **System prompt update** — The agent's system prompt in `react_agent.py` is updated to instruct the LLM when to use GraphRAG tools versus product catalog tools. Knowledge search tools are for support questions, troubleshooting, and "how do I fix" queries. Product tools remain for browsing, pricing, and catalog queries.

5. **No new dependencies** — All Cypher queries run through `client.graph.execute_read()`. All embeddings use `client._embedder.embed()`. No import of `neo4j-graphrag` library into the deployed agent. The retriever patterns are reimplemented as direct Cypher queries within the tools, keeping the deployment artifact unchanged.

6. **No changes to existing tools** — `search_products`, `get_product_details`, `get_related_products`, and all memory tools remain unchanged.

### Files Affected

- `src/knowledge_tools.py` — New file. Three tools + `KNOWLEDGE_TOOLS` list.
- `src/react_agent.py` — Import `KNOWLEDGE_TOOLS`, add to `ALL_TOOLS`, update `SYSTEM_PROMPT`.

### Verification

- Deploy to Databricks Model Serving using existing `step1_deploy_agent.py` (no changes needed).
- Query the endpoint with support-style questions ("my shoes feel flat", "Continental outsole peeling") and verify the agent uses knowledge tools and returns entity-grounded answers.
- Query with catalog-style questions ("show me running shoes under $150") and verify the agent still uses product tools correctly.

---

## Phase 2: Agentic Commerce — Memory and Learning

### What Changes

The agent gains long-term memory (user preferences and entity extraction), reasoning traces, and commerce-oriented tools that use accumulated knowledge to personalize interactions.

### Requirements

1. **Long-term memory activation** — The `MemoryClient` already exposes `client.long_term`, but no tools use it. Add a `track_preference` tool that stores user preferences (preferred brands, categories, size, price sensitivity) as entities in long-term memory with POLE+O classification. Add a `get_user_profile` tool that retrieves accumulated preferences for the current user by querying long-term memory.

2. **Entity extraction on conversation messages** — Change `remember_message` to set `extract_entities=True` instead of `False`. This activates the neo4j-agent-memory extraction pipeline, which pulls Person, Organization, Location, and Object entities from conversation text and stores them in the knowledge graph. Extracted entities link back to the originating message via EXTRACTED_FROM relationships.

3. **Reasoning traces** — Add a `record_reasoning_trace` tool that opens a ReasoningTrace when the agent begins a multi-step task (product comparison, troubleshooting workflow, purchase recommendation) and records each step with its tool call, result, duration, and success/failure. Add a `recall_past_reasoning` tool that takes a task description and uses semantic similarity to find past reasoning traces for comparable tasks, returning the successful approaches.

4. **Personalized product recommendations** — Add a `recommend_for_user` tool that combines the user's long-term preference profile with GraphRAG knowledge search. The tool queries long-term memory for stored preferences, builds a composite query from those preferences, runs it through the VectorCypherRetriever pattern, and filters/ranks results by preference alignment. A returning customer who previously bought trail shoes and expressed interest in waterproofing gets recommendations grounded in both the knowledge graph and their history.

5. **Cross-session continuity** — The `session_id` currently scopes short-term memory. Add a `user_id` field to `RetailContext` that scopes long-term memory and reasoning traces. Short-term memory remains session-scoped (conversation history). Long-term memory and reasoning traces are user-scoped (persist across sessions). The `user_id` is passed through `custom_inputs` from the calling application.

6. **System prompt update** — Expand the system prompt to instruct the agent on the full tool set: when to store preferences, when to consult past reasoning, when to personalize recommendations. The agent should proactively check user preferences at the start of a session and use past reasoning traces when encountering similar tasks.

### Files Affected

- `src/retail_context.py` — Add `user_id: str | None = None` field.
- `src/serving_adapter.py` — Extract `user_id` from `custom_inputs`, pass to `RetailContext`.
- `src/memory_tools.py` — Change `extract_entities` to `True` in `remember_message`. Add `track_preference`, `get_user_profile` tools.
- `src/reasoning_tools.py` — New file. `record_reasoning_trace`, `recall_past_reasoning` tools + `REASONING_TOOLS` list.
- `src/commerce_tools.py` — New file. `recommend_for_user` tool + `COMMERCE_TOOLS` list.
- `src/react_agent.py` — Import new tool lists, add to `ALL_TOOLS`, update `SYSTEM_PROMPT`.

### Verification

- Deploy and run a multi-turn session where the user states preferences ("I prefer trail running shoes", "I need waterproof"). Verify preferences persist in long-term memory.
- Start a new session with the same `user_id`. Verify the agent retrieves the stored profile and personalizes responses without being told preferences again.
- Trigger a multi-step troubleshooting workflow. Verify reasoning trace is recorded. Ask a similar question in a later session and verify the agent surfaces the past trace.
- Run the existing `step4_demo_agent.py` sample queries and verify no regression in basic product search and memory behavior.

---

## What This Does Not Include

- **No changes to the Neo4j schema or data pipeline.** Phase 1 consumes the graph that `step2_load_products.py` and `step3_load_graphrag.py` already build. Phase 2 uses neo4j-agent-memory's built-in schema for long-term memory and reasoning traces.
- **No new model endpoints.** Both phases use the existing `databricks-claude-sonnet-4-6` LLM endpoint and `databricks-bge-large-en` embedding endpoint.
- **No external service integrations.** No payment processing, no inventory management APIs, no external enrichment. Those are future work beyond this proposal.
- **No changes to `step1_deploy_agent.py`, `step2_load_products.py`, `step3_load_graphrag.py`, or `step5_demo_retrievers.py`.**
