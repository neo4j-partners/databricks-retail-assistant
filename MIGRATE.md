# Migration Proposal: Replace Manual GraphRAG Pipeline with neo4j-graphrag-python

## Goal

Replace the hand-rolled GraphRAG pipeline in `step3_load_graphrag.py` (roughly 400 lines of custom chunking, embedding, LLM entity extraction, and Cypher writes) with Neo4j's official `neo4j-graphrag-python` library. This is a complete replacement, not a partial compatibility shim. All graph data (products, knowledge, entities, chunks) will be fully rebuilt from scratch each time the pipeline runs.

## Why

The current `step3_load_graphrag.py` manually implements chunking, embedding, LLM-based entity extraction, JSON parsing, and Cypher node/relationship writes. The `neo4j-graphrag-python` library does all of this out of the box through its `SimpleKGPipeline`, with added benefits: built-in JSON repair for malformed LLM responses, schema-aware extraction with pruning, and pluggable entity resolution (exact, fuzzy, or semantic). Switching to it means less code to maintain, fewer bugs from hand-rolled JSON parsing, and access to improvements the Neo4j team ships in future releases.

The library has no built-in Databricks or mlflow integration, but it exposes clean abstract classes (`Embedder` and `LLMInterfaceV2`) that make it straightforward to wrap the Databricks Foundation Model API. Two small adapter classes are all that's needed.

## What Changes

This migration touches the data-loading pipeline only. The agent itself (the LangGraph ReAct loop, the serving adapter, the tool definitions) is not changing. But because the neo4j-graphrag-python library writes a slightly different graph structure than the current hand-rolled pipeline, the agent's Cypher queries in the tool files need to be updated to match. Everything gets rebuilt from scratch, so there is no partial compatibility concern.

### Graph Schema Differences

The current pipeline writes this structure:

- Source document nodes (`KnowledgeArticle`, `SupportTicket`, `Review`) linked to `Chunk` nodes via `HAS_CHUNK`
- Entity nodes (`Feature`, `Symptom`, `Solution`) linked from chunks via `MENTIONS_FEATURE`, `REPORTS_SYMPTOM`, `PROVIDES_SOLUTION`
- Product-level entity links via `HAS_FEATURE`, `HAS_SYMPTOM`, `HAS_SOLUTION`
- Sequential chunk links via `NEXT_CHUNK`

The neo4j-graphrag-python library writes a "lexical graph" with its own conventions:

- A `Document` node linked to `Chunk` nodes via `FROM_DOCUMENT` (instead of per-source-type nodes linked via `HAS_CHUNK`)
- Entity nodes get an additional `__Entity__` label alongside their custom label
- Entities link back to their source chunk via `FROM_CHUNK` (instead of `MENTIONS_FEATURE` etc.)
- Sequential chunks linked via `NEXT_CHUNK` (same as current)

All of these label and relationship names are configurable through the library's `LexicalGraphConfig` and `GraphSchema` classes. So we have two options: configure the library to match the current schema exactly, or update the agent's Cypher queries to use the library's defaults. The plan below investigates both during prototyping and picks the cleanest approach.

### What Stays the Same

- `step2_load_products.py` is unchanged. It writes Product, Category, Brand, and Attribute nodes via the Spark Connector. Those nodes exist before the GraphRAG pipeline runs.
- The product catalog data (`data/product_catalog.py`) and knowledge data (`data/product_knowledge.py`) are unchanged.
- The agent's architecture (LangGraph, ToolRuntime, MLflow serving) is unchanged.
- The deploy config (`src/deploy_config.py`) is unchanged, though the adapter classes will read `CONFIG.embedding_model`, `CONFIG.llm_endpoint`, and `CONFIG.embedding_dimensions` from it.

## Plan

### Phase 1: Verify the Databricks CLI Can Run Python Remotely -- COMPLETE

Before writing any code, confirm that we can iterate quickly by running Python scripts on a Databricks cluster from the local terminal. This avoids the slow loop of uploading notebooks through the workspace UI.

**What to check:**

The Databricks CLI `jobs submit` command can run a one-time job without saving it. The command accepts a `--json` flag with a job definition that includes a `spark_python_task` pointing to a Python file. The file needs to be uploaded to the workspace first using `databricks workspace import`.

The workflow would be:

1. Upload a test script to the workspace: `databricks workspace import ./test_script.py /Workspace/Users/<user>/dbx_rd/test_script.py`
2. Submit a one-time run: `databricks jobs submit --json @job_def.json` where the JSON references the uploaded script and an existing cluster
3. Check the output in the CLI or the Databricks UI runs page

Relevant Databricks documentation:
- [Databricks CLI command reference](https://docs.databricks.com/aws/en/dev-tools/cli/commands) — full list of CLI command groups
- [jobs command group](https://docs.databricks.com/aws/en/dev-tools/cli/reference/jobs-commands) — `jobs submit`, `jobs create`, `jobs run-now`
- [Python script task for jobs](https://docs.databricks.com/aws/en/jobs/python-script) — configuring `spark_python_task` with python_file path
- [workspace command group](https://docs.databricks.com/aws/en/dev-tools/cli/reference/workspace-commands) — `workspace import` for uploading files
- [Automate job creation and management](https://docs.databricks.com/aws/en/jobs/automate) — end-to-end examples of CLI-driven job workflows

An alternative to `jobs submit` is Databricks Connect, which lets you run Python directly from a local IDE against a remote cluster. But `jobs submit` is simpler for one-off pipeline scripts and doesn't require a persistent Spark session.

**Outcome:** A working local-to-Databricks execution loop. If `jobs submit` with `spark_python_task` works, we use that for all prototyping. If not, fall back to Databricks Connect or manual notebook upload.

**Status: COMPLETE** -- Verified 2026-03-11. The three-script workflow (`upload.sh`, `validate.sh`, `submit.sh`) in `dbx_rd/` works end-to-end. See `dbx_rd/README.md` for usage details.

Results from the test run:
- Cluster: "Small Spark 4.0" (`1029-205109-yca7gn2n`), Databricks Runtime 17.3
- Python 3.12.3, Spark 4.0.0, mlflow 3.10.1, neo4j driver 6.1.0
- Upload + validate + submit round-trip: ~37 seconds on a running cluster
- Job submitted via `databricks jobs submit` with `spark_python_task` and `existing_cluster_id`
- Output retrieved via `databricks jobs get-run-output RUN_ID --profile PROFILE -o json`

Key learnings:
- `databricks workspace mkdirs` is needed before first upload (the remote directory is not auto-created)
- `databricks workspace import` requires `--file`, `--format AUTO`, `--language PYTHON`, and `--overwrite` flags
- `databricks jobs submit` creates a one-time run that does not appear as a saved job in the UI
- `databricks jobs get-run-output` takes the task-level `run_id` (not the top-level job `run_id`) as a positional argument, not a `--run-id` flag
- Using `existing_cluster_id` avoids cluster startup time; the cluster auto-starts if terminated but is much faster when already running

### Phase 2: Build the Databricks Adapter Classes -- COMPLETE

Create two standalone adapter classes in `dbx_rd/`. These wrap the Databricks Foundation Model API (via mlflow) so the neo4j-graphrag-python library can use Databricks-hosted models for embeddings and LLM calls. The prototype is completely self-contained: a copy of `deploy_config.py` lives in `dbx_rd/` alongside the adapters so everything can be uploaded and run on the cluster without depending on files outside the directory.

**Status: COMPLETE** -- Verified 2026-03-11. All three smoke tests passed on the Databricks cluster.

**Prerequisites confirmed:**

- `neo4j-graphrag>=1.13.0` is installed on the cluster (verified from the cluster's library list), so the adapter classes can import `neo4j_graphrag.embeddings.base.Embedder` and `neo4j_graphrag.llm.base.LLMInterfaceV2` directly.
- The existing `DatabricksEmbedder` in `retail_agent/src/databricks_embedder.py` implements a different interface (async-first with `embed`/`embed_batch`/`dimensions` for `neo4j-agent-memory`). The Phase 2 adapters are standalone classes designed specifically for the neo4j-graphrag-python library's `Embedder` and `LLMInterfaceV2` interfaces. They do not wrap or depend on the existing embedder.
- Working prototype adapter classes already exist in `retail_agent/step5_demo_retrievers.py` (lines 69–121). These were written for the retriever demo and confirm the mlflow integration pattern works. The Phase 2 adapters will follow the same pattern but as standalone files with validation and error handling.

**DatabricksEmbedder**

Subclasses `Embedder` from `neo4j_graphrag.embeddings.base`. Implements one required method: `embed_query(text: str) -> list[float]`. Inside, it calls `mlflow.deployments.get_deploy_client("databricks").predict(endpoint=..., inputs={"input": [text]})` and returns the embedding vector. The endpoint name and dimensions come from `deploy_config.py` (`CONFIG.embedding_model` = `databricks-bge-large-en`, `CONFIG.embedding_dimensions` = 1024).

The base class provides a default `async_embed_query` that delegates to `embed_query` synchronously. This is the standard pattern across all embedder implementations in the neo4j-graphrag-python library (OpenAI, Cohere, SentenceTransformer — none of them override `async_embed_query`). No async override is needed.

**DatabricksLLM**

Subclasses `LLMInterfaceV2` from `neo4j_graphrag.llm.base`. Implements two required methods:

- `invoke(input: List[LLMMessage], response_format=None, **kwargs) -> LLMResponse` — calls `mlflow.deployments.get_deploy_client("databricks").predict(endpoint=..., inputs={"messages": ..., "max_tokens": ...})` and returns an `LLMResponse(content=...)` from the response's `choices[0].message.content`.

- `ainvoke(input: List[LLMMessage], response_format=None, **kwargs) -> LLMResponse` — delegates to `invoke` synchronously (i.e., `return self.invoke(input, response_format=response_format)`).

The `ainvoke` delegates to `invoke` because `mlflow.deployments` has no async client. Every LLM implementation in the neo4j-graphrag-python library uses a native async client for `ainvoke` (OpenAI uses `AsyncOpenAI`, Anthropic uses `AsyncAnthropic`, Cohere uses `AsyncClientV2`). Since mlflow has no async equivalent, the cleanest approach is synchronous delegation. This matches the pattern already proven in `step5_demo_retrievers.py` and the embedder base class's own `async_embed_query` default. If async throughput becomes a bottleneck in Phase 4, `ainvoke` could be updated to use `asyncio.get_event_loop().run_in_executor()` (the same pattern used in the existing `databricks_embedder.py`), but for the pipeline workload this is unnecessary.

The endpoint name comes from `deploy_config.py` (`CONFIG.llm_endpoint` = `databricks-claude-sonnet-4-6`).

**What gets uploaded to the cluster:**

- `deploy_config.py` — copy of the config singleton (provides endpoint names and dimensions)
- `databricks_embedder.py` — the embedder adapter
- `databricks_llm.py` — the LLM adapter
- `test_adapters.py` — smoke test that imports both adapters, embeds a sentence, sends a chat message, and prints results

Both adapter classes authenticate through the cluster's own identity via mlflow — no API keys needed.

**Outcome:** Standalone adapter files in `dbx_rd/` verified by a smoke test on the Databricks cluster using the Phase 1 execution loop (upload, submit, check output). The smoke test confirms: embedding returns a vector of the expected dimensions, and the LLM returns a coherent text response.

Results from the smoke test run (2026-03-11):

- `DatabricksEmbedder.embed_query("lightweight running shoes for beginners")` returned a 1024-dimension vector. Confirmed `isinstance(embedder, Embedder)` is True.
- `DatabricksLLM.invoke([{"role": "user", "content": "..."}])` returned an `LLMResponse` with correct content. Confirmed `isinstance(llm, LLMInterfaceV2)` is True.
- `DatabricksLLM.invoke("plain string")` (V1 compat) also works, needed for `Text2CypherRetriever`.
- Execution time: ~20 seconds on the running cluster (includes mlflow client initialization and two API calls).

### Phase 3: Investigate Schema Compatibility -- COMPLETE

This is the most important investigation step. The agent's tool files (`knowledge_tools.py`, `commerce_tools.py`, `product_tools.py`) contain hardcoded Cypher queries that expect specific node labels, relationship types, and property names. The neo4j-graphrag-python library's output needs to match what those queries expect, or the queries need to be updated.

**Status: COMPLETE** -- Investigated 2026-03-11. Full findings and the Phase 4 implementation plan are in `MIGRATE_V4.md`.

**Decision: Update the agent's Cypher queries to match the library's output.** The library cannot produce the current per-entity-type relationship names (`MENTIONS_FEATURE`, `REPORTS_SYMPTOM`, `PROVIDES_SOLUTION`) because `LexicalGraphConfig.node_to_chunk_relationship_type` is a single value shared across all entity types. Configuring it to match one type would break the other two. Updating the queries is the cleaner path.

**Key findings:**

1. `LexicalGraphConfig` controls all lexical graph labels and property names, but `node_to_chunk_relationship_type` is a single value — it cannot produce per-entity-type relationship names. This is the fundamental incompatibility.

2. The `chunk_to_document_relationship_type` goes from chunk to document (`(chunk)-[:FROM_DOCUMENT]->(document)`), which is the opposite direction from the current `(document)-[:HAS_CHUNK]->(chunk)`. Renaming it would not fix the direction mismatch. `HAS_CHUNK` must be created by a post-pipeline Cypher step.

3. `SimpleKGPipeline` creates its own `Document` nodes — it does not link to pre-existing nodes. Document metadata (`source_type`, `source_id`) can be passed so the post-pipeline step can match chunks to existing `KnowledgeArticle`/`SupportTicket`/`Review` nodes via the `Document` bridge.

4. Entity nodes get an `__Entity__` label alongside their custom label. This is harmless — all agent queries match specific labels (`Feature`, `Symptom`, `Solution`).

5. `chunk_id_property` can be set to `"chunk_id"` in `LexicalGraphConfig` so the library stores chunk IDs under `chunk_id` instead of `id`, maintaining compatibility with queries that reference `node.chunk_id`.

6. Chunk metadata (e.g., `source_type`) flows through as regular node properties, so custom properties survive the pipeline.

7. The library's `Neo4jWriter` uses APOC procedures (`apoc.create.addLabels`, `apoc.merge.relationship`). Neo4j Aura includes APOC Core, so this works without additional setup.

8. Entity resolution (`perform_entity_resolution=True`) replaces the current `MERGE (f:Feature {name: name})` pattern — the library handles deduplication automatically.

**Outcome:** See `MIGRATE_V4.md` for the complete change list, post-pipeline Cypher steps, and file-by-file update plan for Phase 4.

### Phase 4: Update the Project

With the adapters tested and the schema approach decided, do the actual migration. Since all data is rebuilt from scratch, there is no partial compatibility period.

**Detailed implementation plan is in `MIGRATE_V4.md`**, which covers:

- LexicalGraphConfig settings (only `chunk_id_property` needs overriding)
- GraphSchema definition (Feature, Symptom, Solution node types)
- Document feeding strategy (how to handle articles, tickets, reviews)
- Four post-pipeline Cypher steps (HAS_CHUNK linkage, product shortcuts, indexes, optional cleanup)
- File-by-file Cypher query changes (knowledge_tools.py, commerce_tools.py, step5_demo_retrievers.py)
- Seven implementation steps from rewrite through end-to-end validation
- Risk assessment and APOC dependency notes

**Summary of changes:**

1. Rewrite `step3_load_graphrag.py` to use `SimpleKGPipeline` with `DatabricksEmbedder` and `DatabricksLLM`.
2. Move adapter classes from `dbx_rd/` into `retail_agent/src/`.
3. Update Cypher queries in `knowledge_tools.py` and `commerce_tools.py` — replace `MENTIONS_FEATURE`/`REPORTS_SYMPTOM`/`PROVIDES_SOLUTION` with reversed `FROM_CHUNK` pattern.
4. Update retriever queries in `step5_demo_retrievers.py` (same relationship changes) and replace inline adapter classes with imports.
5. No changes needed in `product_tools.py` or `step6_check_knowledge.py`.
6. Add `neo4j-graphrag-python` as a project dependency.
7. Run full end-to-end validation, then delete `dbx_rd/`.

**Outcome:** A working agent with the same capabilities as today, but with the GraphRAG pipeline powered by neo4j-graphrag-python instead of custom code. The `dbx_rd/` folder is gone, the adapter classes live in `src/`, and the graph is fully rebuilt.
