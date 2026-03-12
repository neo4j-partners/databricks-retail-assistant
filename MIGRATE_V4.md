# Phase 4 Implementation Plan

This document captures the Phase 3 schema compatibility findings and lays out the detailed implementation plan for Phase 4 — the final migration from the hand-rolled GraphRAG pipeline to neo4j-graphrag-python.

## Resolved Questions

All questions resolved before implementation. Answers inline.

1. **Embedder name collision** — The new adapters will replace the existing embedder eventually. Don't worry about naming for now.
2. **Cross-entity subqueries** — Deferred to a later phase. Build the initial prototype first without updating agent tool Cypher queries.
3. **Graph cleanup** — Keep simple for prototype. Database will be reset manually as needed.
4. **Sync driver** — Yes, use sync `neo4j.GraphDatabase.driver()` (required by `SimpleKGPipeline`).
5. **`from_pdf=False`** — Must be set in `SimpleKGPipeline` constructor since we pass text, not PDFs.
6. **`nest_asyncio`** — Still needed on Databricks for `run_async()`. Carry over the same pattern from the current step3.
7. **Documentation files** — Deferred. `EXPAND.md` and `docs/DevelopersGuideGraphRAG-Databricks.md` will be updated in a later phase.

---

## Phase 3 Findings: Schema Compatibility

### The Fundamental Incompatibility

The current pipeline writes three different entity-to-chunk relationship types based on entity label:

- `(Chunk)-[:MENTIONS_FEATURE]->(Feature)`
- `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom)`
- `(Chunk)-[:PROVIDES_SOLUTION]->(Solution)`

The neo4j-graphrag-python library writes a single relationship type for all entities:

- `(Feature)-[:FROM_CHUNK]->(Chunk)`
- `(Symptom)-[:FROM_CHUNK]->(Chunk)`
- `(Solution)-[:FROM_CHUNK]->(Chunk)`

`LexicalGraphConfig.node_to_chunk_relationship_type` is one value shared across all entity types. There is no per-entity-type override. This means the library cannot produce the current schema's per-type relationship naming.

Additionally, the direction is reversed: the library writes entity→chunk (`FROM_CHUNK`), while the current schema writes chunk→entity (`MENTIONS_FEATURE`, etc.).

### The Document Node Gap

The current pipeline links chunks to pre-existing document nodes created by step2:

- `(KnowledgeArticle)-[:HAS_CHUNK]->(Chunk)`
- `(SupportTicket)-[:HAS_CHUNK]->(Chunk)`
- `(Review)-[:HAS_CHUNK]->(Chunk)`

The library creates its own `Document` nodes and links chunks to them:

- `(Chunk)-[:FROM_DOCUMENT]->(Document)`

The `chunk_to_document_relationship_type` config controls the name but not the direction. It goes chunk→document, not document→chunk. `SimpleKGPipeline` does not know about or link to pre-existing nodes.

### What the Library Can Match

These aspects of the current schema are already compatible or configurable:

| Element | Current | Library Default | Configurable? | Action |
|---------|---------|----------------|---------------|--------|
| Chunk label | `Chunk` | `Chunk` | Yes | No change needed |
| Chunk text property | `text` | `text` | Yes | No change needed |
| Chunk embedding property | `embedding` | `embedding` | Yes | No change needed |
| Chunk ID property | `chunk_id` | `id` | Yes (`chunk_id_property`) | Configure to `chunk_id` |
| NEXT_CHUNK | `NEXT_CHUNK` | `NEXT_CHUNK` | Yes | No change needed |
| Entity labels | `Feature`, `Symptom`, `Solution` | Same (via GraphSchema) | Yes | No change needed |
| Entity `name` property | `name` | `name` (via schema) | Yes | No change needed |
| `__Entity__` extra label | Not present | Added to all entities | N/A | Harmless — queries match specific labels |

### What Cannot Be Matched

| Element | Current | Library Output | Why |
|---------|---------|---------------|-----|
| Entity-to-chunk relationships | 3 types (`MENTIONS_FEATURE`, etc.) | 1 type (`FROM_CHUNK`) | Single config value |
| Entity-to-chunk direction | Chunk→Entity | Entity→Chunk | Library convention |
| Document-to-chunk | Doc→Chunk (`HAS_CHUNK`) | Chunk→Doc (`FROM_DOCUMENT`) | Library convention |
| Document node type | `KnowledgeArticle`, etc. | `Document` | Library creates its own |

### Decision

**Update the agent's Cypher queries to match the library's output.** This is cleaner than fighting the library's conventions. The query changes are mechanical — same traversal patterns, just different relationship names and directions.

---

## LexicalGraphConfig Settings

```
chunk_id_property: "chunk_id"     # maintain node.chunk_id compatibility
chunk_node_label: "Chunk"         # default, no change
chunk_text_property: "text"       # default, no change
chunk_embedding_property: "embedding"  # default, no change
next_chunk_relationship_type: "NEXT_CHUNK"  # default, no change
node_to_chunk_relationship_type: "FROM_CHUNK"  # default, no change
chunk_to_document_relationship_type: "FROM_DOCUMENT"  # default, no change
document_node_label: "Document"   # default, no change
```

Only `chunk_id_property` needs to be overridden from the default.

## GraphSchema Definition

The schema tells the LLM what entity and relationship types to extract. Node types and relationship types are passed as simple strings — the library auto-adds a `name` property and sets `additional_properties=True` for flexible extraction (see "Key Patterns Learned" above).

```python
SCHEMA = {
    "node_types": ["Feature", "Symptom", "Solution"],
    "relationship_types": ["HAS_FEATURE", "HAS_SYMPTOM", "HAS_SOLUTION", "RELATED_TO"],
    "patterns": [
        ("Feature", "RELATED_TO", "Symptom"),
        ("Symptom", "HAS_SOLUTION", "Solution"),
        ("Feature", "RELATED_TO", "Solution"),
    ],
}
```

These are entity-to-entity relationships extracted by the LLM, separate from the lexical graph relationships (`FROM_CHUNK`, `FROM_DOCUMENT`). The library creates the entity-to-chunk links automatically via `FROM_CHUNK`.

## Document Feeding Strategy

The current step3 processes three document types with different chunking:

- **Knowledge articles**: 1 chunk per article (full `content` field)
- **Support tickets**: 2 chunks per ticket (`issue_description` + `resolution_text`)
- **Reviews**: 1 chunk per review (full `raw_text` field)

With `SimpleKGPipeline`, each call to `run_async(text=...)` processes one text document. The library's text splitter (default: `FixedSizeSplitter`, 2000 chars, 200 overlap) handles chunking. For texts shorter than the chunk size, it produces one chunk — matching the current behavior for most articles and reviews.

For support tickets, the simplest approach is to concatenate `issue_description` and `resolution_text` with a separator and feed as one document. The splitter will handle chunking, and `NEXT_CHUNK` relationships are created automatically between consecutive chunks.

Each document call passes metadata so the post-pipeline step can link chunks back to existing nodes:

```
document_metadata = {
    "source_type": "KnowledgeArticle",  # or "SupportTicket", "Review"
    "source_id": article_id              # or ticket_id, review_id
}
```

This metadata becomes properties on the `Document` node, which the post-pipeline Cypher uses as a bridge.

## Post-Pipeline Cypher Steps

These run after all documents have been processed through `SimpleKGPipeline`.

### Step 1: Link chunks to existing document nodes via HAS_CHUNK

The library's `Document` nodes have `source_type` and `source_id` in their properties (from `document_metadata`). Use these to bridge to existing nodes:

```
For KnowledgeArticle:
  MATCH (ch:Chunk)-[:FROM_DOCUMENT]->(d:Document {source_type: 'KnowledgeArticle'})
  MATCH (ka:KnowledgeArticle {article_id: d.source_id})
  MERGE (ka)-[:HAS_CHUNK]->(ch)
  SET ch.source_type = 'KnowledgeArticle'

For SupportTicket:
  MATCH (ch:Chunk)-[:FROM_DOCUMENT]->(d:Document {source_type: 'SupportTicket'})
  MATCH (st:SupportTicket {ticket_id: d.source_id})
  MERGE (st)-[:HAS_CHUNK]->(ch)
  SET ch.source_type = 'SupportTicket'

For Review:
  MATCH (ch:Chunk)-[:FROM_DOCUMENT]->(d:Document {source_type: 'Review'})
  MATCH (r:Review {review_id: d.source_id})
  MERGE (r)-[:HAS_CHUNK]->(ch)
  SET ch.source_type = 'Review'
```

This creates the `HAS_CHUNK` relationships the agent queries expect and sets `source_type` on chunks (used in RETURN clauses).

### Step 2: Create product-level entity shortcuts

Same as the current `_link_entities_to_products` function, but with the reversed `FROM_CHUNK` direction:

```
MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch)<-[:FROM_CHUNK]-(f:Feature)
MERGE (p)-[:HAS_FEATURE]->(f)

MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch)<-[:FROM_CHUNK]-(s:Symptom)
MERGE (p)-[:HAS_SYMPTOM]->(s)

MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch)<-[:FROM_CHUNK]-(sol:Solution)
MERGE (p)-[:HAS_SOLUTION]->(sol)
```

### Step 3: Create indexes

Vector and fulltext indexes are not created by the library. These must be created manually, same as today:

```
Vector index: chunk_embedding on Chunk.embedding (cosine, CONFIG.embedding_dimensions)
Fulltext index: chunkText on Chunk.text (english analyzer)
```

The product_embedding vector index on Product.embedding is created by step2 and is not affected by this migration.

### Step 4: (Optional) Clean up Document nodes

The library's `Document` nodes are intermediary. After `HAS_CHUNK` relationships have been created from the real document nodes, the `Document` nodes are no longer needed for query traversal. They can be left in place (they don't interfere) or deleted:

```
MATCH (d:Document) DETACH DELETE d
```

Leaving them adds no cost and provides traceability, so the recommendation is to leave them.

---

## Cypher Query Changes by File

### knowledge_tools.py

**knowledge_search** — 4 relationship changes:

```
Before: (node)-[:MENTIONS_FEATURE]->(f:Feature)
After:  (f:Feature)-[:FROM_CHUNK]->(node)

Before: (node)-[:REPORTS_SYMPTOM]->(s:Symptom)
After:  (s:Symptom)-[:FROM_CHUNK]->(node)

Before: (node)-[:PROVIDES_SOLUTION]->(sol:Solution)
After:  (sol:Solution)-[:FROM_CHUNK]->(node)

Before: (other)<-[:HAS_CHUNK]-(doc)-[:COVERS|ABOUT|REVIEWS]->(p:Product)
After:  (same — HAS_CHUNK is created by post-pipeline step, direction unchanged)
```

The `collect` subquery pattern changes from:
```
collect { MATCH (node)-[:MENTIONS_FEATURE]->(f:Feature) RETURN f.name } AS features
```
to:
```
collect { MATCH (f:Feature)-[:FROM_CHUNK]->(node) RETURN f.name } AS features
```

**hybrid_knowledge_search** — same 4 relationship changes as knowledge_search.

**diagnose_product_issue (Variant A, with embedding)** — 3 relationship changes:

```
Before: (ch)-[:REPORTS_SYMPTOM]->(s:Symptom)
After:  (s:Symptom)-[:FROM_CHUNK]->(ch)

Before: (ch)-[:PROVIDES_SOLUTION]->(sol:Solution)
After:  (sol:Solution)-[:FROM_CHUNK]->(ch)

Before: (ch)-[:MENTIONS_FEATURE]->(f:Feature)
After:  (f:Feature)-[:FROM_CHUNK]->(ch)
```

**diagnose_product_issue (Variant B, no embedding)** — no changes. Uses `HAS_SYMPTOM`, `HAS_SOLUTION`, `HAS_FEATURE` which are product-level shortcuts created by the post-pipeline step.

### commerce_tools.py

**recommend_for_user** — 2 relationship changes:

```
Before: (node)-[:MENTIONS_FEATURE]->(f:Feature)
After:  (f:Feature)-[:FROM_CHUNK]->(node)

Before: (node)-[:REPORTS_SYMPTOM]->(s:Symptom)
After:  (s:Symptom)-[:FROM_CHUNK]->(node)
```

`HAS_CHUNK` and `COVERS|ABOUT|REVIEWS` are unchanged.

### product_tools.py

**No changes needed.** All queries in this file operate on Product, Category, Brand, and Attribute nodes. None traverse the GraphRAG layer (chunks, entities, FROM_CHUNK).

### step5_demo_retrievers.py

**VECTOR_CYPHER_QUERY** — 4 relationship changes (same pattern as knowledge_search).

**HYBRID_CYPHER_QUERY** — 4 relationship changes (same pattern as hybrid_knowledge_search).

**TEXT2CYPHER_EXAMPLES** — no changes. The examples use `HAS_SYMPTOM`, `HAS_SOLUTION`, `HAS_FEATURE`, `IN_CATEGORY` — all product-level shortcuts or step2 relationships, not chunk-entity relationships.

**Adapter classes** — the `DatabricksEmbeddings` and `DatabricksLLM` classes in this file will be replaced with imports from the new standalone adapter files in `retail_agent/src/`.

### step6_check_knowledge.py

**No direct Cypher changes.** This file tests the agent endpoint, which calls the tools above. The query changes flow through the tool updates.

### step3_load_graphrag.py

**Complete rewrite.** The entire file is replaced with a new implementation using `SimpleKGPipeline`. See the implementation plan below.

---

## Phase 4 Implementation Plan

Phase 4 is split into two stages: prototype the pipeline in `dbx_rd/` first, then integrate into the main project later.

### Phase 4a: Prototype in `dbx_rd/` -- COMPLETE

Build a standalone `load_graphrag.py` in `dbx_rd/` that runs the full pipeline on the Databricks cluster using the existing upload/submit workflow. This proves the `SimpleKGPipeline` approach works end-to-end before touching any files in `retail_agent/`.

**Step 1: Create `dbx_rd/load_graphrag.py` -- COMPLETE**

Created `dbx_rd/load_graphrag.py` — a standalone prototype that:

1. Gets Neo4j credentials from Databricks secrets (same pattern as existing step scripts).
2. Creates a sync `neo4j.GraphDatabase.driver()` connection (required by `SimpleKGPipeline`).
3. Fetches document text directly from Neo4j nodes created by step2 (KnowledgeArticle, SupportTicket, Review) — avoids dependency on the `retail_agent` data package.
4. Imports `DatabricksEmbedder` and `DatabricksLLM` from the Phase 2 adapters already in `dbx_rd/`.
5. Defines a `GraphSchema` with Feature, Symptom, Solution node types (as strings) and HAS_FEATURE, HAS_SYMPTOM, HAS_SOLUTION, RELATED_TO relationship types (as strings).
6. Configures `LexicalGraphConfig` with `chunk_id_property="chunk_id"`.
7. Creates a `SimpleKGPipeline` with `from_pdf=False`, the LLM, driver, embedder, schema, and config.
8. Loops over all documents, calling `pipeline.run_async(text=..., document_metadata={"source_type": ..., "source_id": ...})` for each.
9. Runs post-pipeline Cypher steps (HAS_CHUNK linkage, product-level shortcuts, vector and fulltext indexes).
10. Prints verification counts for all node labels and relationship types.

Uses `nest_asyncio.apply()` for Databricks event loop compatibility. No graph cleanup — database is reset manually before each run.

For support tickets, concatenates `issue_description` and `resolution_text` with a separator, matching the strategy in the plan.

**Step 2: Upload and run on Databricks -- COMPLETE**

Successfully ran on 2026-03-12 after fixing two issues (see "Issues Fixed" below).

**Results:**

| Node / Relationship | Count |
|---------------------|-------|
| Chunks | 252 |
| Documents | 252 |
| Features | 529 |
| Symptoms | 422 |
| Solutions | 507 |
| FROM_CHUNK rels | 1,578 |
| FROM_DOCUMENT rels | 252 |
| HAS_CHUNK rels | 252 |
| HAS_FEATURE rels | 557 |
| HAS_SYMPTOM rels | 425 |
| HAS_SOLUTION rels | 1,102 |
| NEXT_CHUNK rels | 0 |

All 252 documents processed, 0 failures. Two minor "LLM response has improper format" warnings (handled by `on_error="IGNORE"`). NEXT_CHUNK is 0 because each document produced a single chunk (texts are shorter than the 2000-char default split size).

**Verification criteria — all met:**
- All 252 documents processed without errors
- Chunk nodes have embeddings (1,024 dims via `databricks-bge-large-en`)
- Entity nodes created: 529 Features, 422 Symptoms, 507 Solutions
- 1,578 `FROM_CHUNK` relationships from entities to chunks
- 252 `HAS_CHUNK` relationships created by post-pipeline Cypher
- Product-level shortcuts created: 557 `HAS_FEATURE`, 425 `HAS_SYMPTOM`, 1,102 `HAS_SOLUTION`
- Vector index (`chunk_embedding`) and fulltext index (`chunkText`) created

---

### Issues Fixed During Step 2

**Issue 1: LLMInterface V1 vs V2 incompatibility**

`SimpleKGPipelineConfig` validates with `isinstance(llm, LLMInterface)`. Our `DatabricksLLM` originally extended `LLMInterfaceV2`, a completely separate class hierarchy — `LLMInterfaceV2` does NOT inherit from `LLMInterface`. Both extend `ABC` independently.

The pipeline config's `LLMType` validator (`object_config.py:202`) accepts `Union[LLMInterface, LLMConfig]` — no `LLMInterfaceV2`. The entity extractor calls `await self.llm.ainvoke(prompt)` with a plain string (V1 signature).

This is true in the latest release (1.13.1). `LLMInterface` is deprecated but remains the only interface accepted by the pipeline.

**Fix:** Changed `DatabricksLLM` to extend `LLMInterface` (V1). Updated method signatures from `(input: Union[str, List[LLMMessage]], response_format, **kwargs)` to `(input: str, message_history, system_instruction)`. Added proper handling of `system_instruction` and `message_history` parameters. The `LLMInterface` constructor logs a deprecation warning — expected and harmless.

Note: `LLMInterfaceV2` is still needed by retrievers (`VectorCypherRetriever`, `Text2CypherRetriever`, `GraphRAG`) used in `step5_demo_retrievers.py`. That file has its own inline `DatabricksLLM(LLMInterfaceV2)` class, so there's no conflict.

**Issue 2: Schema node types require properties (1.13.x)**

In neo4j-graphrag 1.13.x, `NodeType` has `properties: list[PropertyType] = Field(min_length=1)` — node types require at least 1 property. Our schema used dicts with `label` and `description` but no `properties`, causing a `ValidationError`.

The library provides a string shorthand: passing `"Feature"` instead of `{"label": "Feature", ...}` triggers a model validator that auto-adds `{"name": "name", "type": "STRING"}` with `additional_properties=True`, allowing the LLM to freely extract properties beyond just `name`.

**Fix:** Changed schema `node_types` and `relationship_types` from dicts to simple strings. This is the library's recommended pattern for flexible extraction (see `examples/build_graph/simple_kg_builder_from_text.py`).

---

### Key Patterns Learned

1. **LLMInterface V1 for pipelines, V2 for retrievers** — The `SimpleKGPipeline` and its components (entity extractor, schema builder) use `LLMInterface` (V1) exclusively. `LLMInterfaceV2` is used by retrievers (`VectorCypherRetriever`, `Text2CypherRetriever`, `GraphRAG`). Custom LLM adapters may need both versions depending on usage.

2. **Schema strings over dicts** — For node types, pass simple strings (e.g., `"Feature"`) unless you need explicit property constraints. The library auto-adds a `name` property and sets `additional_properties=True` for flexible LLM extraction. Dicts with `label`+`description` but no `properties` fail validation in 1.13.x.

3. **Databricks `SystemExit: 0` is success** — Databricks treats `sys.exit(0)` as a failure (`INTERNAL_ERROR`). Check the logs, not the exit status.

4. **`on_error="IGNORE"` is essential** — LLM extraction occasionally produces malformed responses. Without `on_error="IGNORE"`, a single bad response would fail the entire pipeline. With it, the pipeline logs a warning and continues.

5. **Single-chunk documents** — With the default `FixedSizeSplitter` (2000 chars, 200 overlap), most retail documents produce exactly 1 chunk. This means `NEXT_CHUNK` relationships are not created (expected). For longer documents, the splitter would create multiple chunks with `NEXT_CHUNK` links automatically.

6. **Entity resolution works** — `perform_entity_resolution=True` ran without issues. 252 documents produced ~1,500 entities, with product-level shortcuts creating slightly more relationships (e.g., 557 HAS_FEATURE for 529 Features) — indicating some entities span multiple products.

### Phase 4b: Integration (deferred)

Once the prototype is validated (DONE), integrate into the main project. These steps are deferred:

1. **Move adapter classes from `dbx_rd/` into `retail_agent/src/`**
   - `databricks_llm.py` (V1 interface) — used by pipeline
   - `databricks_embedder.py` — used by pipeline
   - Consider whether a V2 adapter is also needed for retrievers, or if the inline class in `step5_demo_retrievers.py` is sufficient
   - Replaces existing embedder in `serving_adapter.py` (lines 83, 109)

2. **Rewrite `retail_agent/step3_load_graphrag.py`** based on the proven `dbx_rd/load_graphrag.py` prototype. Key differences from the prototype:
   - Import product data from `retail_agent.data` package instead of querying Neo4j
   - Follow the existing step script patterns (error handling, logging)

3. **Update Cypher queries in agent tools** for `FROM_CHUNK` direction changes:
   - `knowledge_tools.py` — `knowledge_search`, `hybrid_knowledge_search`, `diagnose_product_issue` (see detailed Cypher changes above)
   - `commerce_tools.py` — `recommend_for_user` (2 relationship changes)
   - `step5_demo_retrievers.py` — `VECTOR_CYPHER_QUERY`, `HYBRID_CYPHER_QUERY`

4. **Update documentation** — `EXPAND.md`, `docs/DevelopersGuideGraphRAG-Databricks.md`

5. **Add `neo4j-graphrag>=1.13.1` to project dependencies**

6. **End-to-end validation** — Deploy agent, run `step4_demo_agent.py` and `step6_check_knowledge.py` to verify all tools work with the new graph schema

7. **Clean up** — Delete `dbx_rd/` prototyping directory

---

## Risk Assessment

**Low risk:**
- Entity label matching — queries already use specific labels, `__Entity__` is harmless.
- Vector/fulltext indexes — created manually, same as today.
- Product-level shortcuts — same traversal pattern, just reversed `FROM_CHUNK` direction.

**Medium risk:**
- Chunking differences — the library's `FixedSizeSplitter` may produce different chunk boundaries than the current manual chunking. For short texts (most articles and reviews), this is a single chunk and matches exactly. For longer texts, the split points may differ, which could affect vector search relevance slightly.
- LLM extraction quality — the library uses its own prompt template for entity extraction. The current step3 uses a custom prompt with specific instructions ("2-6 words", "lowercase canonical"). The library's GraphSchema description fields can carry similar guidance, but the exact extraction behavior may differ.

**Mitigated by:**
- Complete rebuild from scratch — no partial compatibility concerns.
- End-to-end validation (step 6) catches any regressions.
- Entity resolution handles deduplication automatically.

## APOC Dependency

The library's `Neo4jWriter` uses APOC procedures:
- `apoc.create.addLabels` — add dynamic labels to nodes
- `apoc.merge.relationship` — create or merge relationships

Neo4j Aura includes APOC Core, which provides both of these. No additional setup is needed. If using a self-managed Neo4j instance, APOC Core must be installed.
