# Retail Graph Concierge

This repository builds Retail Graph Concierge, a Databricks-hosted retail assistant backed by Neo4j. The agent can search products, diagnose product issues, answer GraphRAG-backed support questions, remember user preferences, and use those preferences for personalized recommendations.

The current deployment path uses [`databricks-job-runner`](../databricks-job-runner) from a sibling checkout. Local commands build and upload a `retail_agent` wheel, upload thin Databricks job wrappers, submit the six pipeline steps, and validate the deployed Model Serving endpoint.

For the design background behind the graph, GraphRAG, and memory patterns, see [Agentic Commerce: GraphRAG Meets Agent Memory on Neo4j](docs/agentic-commerce.md). For lower-level GraphRAG implementation notes, see [Developer's Guide: GraphRAG on Databricks](docs/DevelopersGuideGraphRAG-Databricks.md).

## Architecture

### Runtime Architecture

```text
Developer machine
  uv + databricks-job-runner
  .env
  cli/
    |
    | upload wrappers + wheel
    v
Databricks Workspace
  /Users/<user>/retail_agent/jobs/*.py
  /Volumes/retail_assistant/retail/retail_volume/wheels/retail_agent-*.whl
    |
    | submit one-time jobs
    v
Databricks Job Cluster
  Step 2: load product graph into Neo4j
  Step 3: build GraphRAG layer in Neo4j
  Step 1: log/register/deploy agent model
  Step 4/5/6: endpoint and retrieval checks
    |
    v
Databricks Model Serving
  MLflow ChatAgent wrapper
  LangGraph ReAct agent
  ChatDatabricks LLM endpoint
    |
    v
Neo4j
  Product graph
  GraphRAG chunks/entities/indexes
  Agent memory
```

### Agent Architecture

The deployed model is an MLflow `ChatAgent` implemented by `retail_agent/agent/serving.py`. It lazily initializes a Neo4j `MemoryClient`, starts a persistent async event loop for the Neo4j async driver, creates the LangGraph ReAct agent, and injects `RetailContext` into tools through `ToolRuntime[RetailContext]`.

The live agent includes these tool groups:

| Tool group | Purpose |
|------------|---------|
| Product tools | Product search, product details, related products |
| Knowledge tools | GraphRAG semantic search, hybrid keyword/vector search, product issue diagnosis |
| Memory tools | Session-scoped remember, recall, and semantic memory search |
| Preference tools | User-scoped long-term preference tracking and profile retrieval |
| Commerce tools | Preference-aware product recommendations using knowledge graph traversal |
| Reasoning tools | Store and recall multi-step reasoning traces |
| Diagnostics | Validate serving-time tool injection and Neo4j/memory initialization |

### Data Architecture

The assistant uses Neo4j as the operational graph for product relationships, GraphRAG retrieval, and agent memory.

| Layer | Main nodes and relationships | Built by |
|-------|------------------------------|----------|
| Product graph | `Product`, `Category`, `Brand`, `Attribute`; `IN_CATEGORY`, `MADE_BY`, `HAS_ATTRIBUTE`, `SIMILAR_TO`, `BOUGHT_TOGETHER` | `step2_load_products.py` |
| Knowledge source graph | `KnowledgeArticle`, `SupportTicket`, `Review`; source document relationships to products | `step2_load_products.py` |
| GraphRAG layer | `Document`, `Chunk`, `Feature`, `Symptom`, `Solution`; `HAS_CHUNK`, `FROM_DOCUMENT`, `MENTIONS_FEATURE`, `REPORTS_SYMPTOM`, `PROVIDES_SOLUTION`, product shortcuts | `step3_load_graphrag.py` |
| Agent memory | `Message`, `Entity`, `Preference`, `Fact`, `Task` and memory vector indexes | `neo4j-agent-memory` at serving time |

Databricks provides the job execution environment, MLflow model registry, Model Serving endpoint, LLM endpoint, embedding endpoint, Unity Catalog volume for wheels, and optional Delta Lake tables for analytics/Genie demos.

## New Features

- `dbx_rd` has been folded into `retail_agent`; the old standalone directory is no longer the runtime path.
- The Databricks workflow now uses `databricks-job-runner` with local `.env` configuration, workspace job wrappers, and wheel uploads to a Unity Catalog volume.
- GraphRAG loading now uses `neo4j-graphrag` `SimpleKGPipeline` with Databricks-native LLM and embedding adapters.
- The GraphRAG layer extracts `Feature`, `Symptom`, and `Solution` entities, links them back to chunks and products, and creates both vector and fulltext indexes.
- The live agent exposes GraphRAG knowledge tools for troubleshooting, hybrid keyword/vector retrieval, and product issue diagnosis.
- The live agent includes short-term memory, long-term user preferences, reasoning trace memory, and preference-aware recommendations.
- Step 1 waits for the target served model version to receive traffic before reporting deployment success.
- Step 4 returns a nonzero status when memory or endpoint checks fail, so Databricks jobs no longer look green when logical checks fail.
- `Chunk.chunk_id` is now populated for GraphRAG retriever compatibility.

## Prerequisites

1. Python 3.12 or newer.
2. `uv` installed locally.
3. Databricks CLI configured with a profile that can access the target workspace.
4. A sibling checkout of `../databricks-job-runner`.
5. A running Databricks cluster for the job steps.
6. Unity Catalog catalog, schema, and volume:
   - `retail_assistant`
   - `retail`
   - `retail_volume`
7. A Neo4j database reachable from Databricks.
8. Databricks model serving access to:
   - `databricks-claude-sonnet-4-6`
   - `databricks-bge-large-en`

Step 2 uses Spark and the Neo4j Spark Connector. Use a dedicated-access cluster and install:

```text
org.neo4j:neo4j-connector-apache-spark_2.12:5.3.1_for_spark_3
```

## Environment Setup

Install local dependencies:

```bash
uv sync
```

Create `.env` from `.env.sample` and fill in the Databricks and Neo4j values:

```env
NEO4J_URI=neo4j+s://<database>.databases.neo4j.io
NEO4J_PASSWORD=<password>

DATABRICKS_PROFILE=<profile>
DATABRICKS_COMPUTE_MODE=cluster
DATABRICKS_CLUSTER_ID=<cluster-id>
DATABRICKS_WORKSPACE_DIR=/Users/<user-email>/retail_agent
DATABRICKS_VOLUME_PATH=/Volumes/retail_assistant/retail/retail_volume

DATABRICKS_WAREHOUSE=<optional-sql-warehouse>
```

Upload Neo4j credentials into the Databricks secret scope used by serving:

```bash
./retail_agent/scripts/setup_databricks_secrets.sh --profile <profile>
```

The script reads `NEO4J_URI` and `NEO4J_PASSWORD` from `.env` and writes them to the `retail-agent-secrets` scope. The runner treats these Neo4j values as local setup inputs and does not forward the password as a job parameter.

Validate the Databricks configuration:

```bash
uv run python -m cli validate
```

## Pipeline Flow

The job wrapper filenames keep the original numbered names, but the recommended full run order is data first, then deploy, then verify.

### 1. Upload Jobs And Wheel

```bash
uv run python -m cli upload --all
uv run python -m cli upload --wheel
```

`upload --all` uploads the wrapper scripts from `jobs/` into `DATABRICKS_WORKSPACE_DIR`. `upload --wheel` builds the current `retail_agent` wheel and uploads it into `DATABRICKS_VOLUME_PATH/wheels`.

### 2. Load Product And Source Knowledge Graph

```bash
uv run python -m cli submit run_retail_agent_step2_load_products.py
```

This creates the retail product graph, source knowledge nodes, product embeddings, and memory indexes in Neo4j.

### 3. Build GraphRAG Layer

```bash
uv run python -m cli submit run_retail_agent_step3_load_graphrag.py
```

This reads `KnowledgeArticle`, `SupportTicket`, and `Review` nodes from Neo4j, runs `SimpleKGPipeline`, creates `Chunk` embeddings, extracts `Feature`, `Symptom`, and `Solution` entities, creates compatibility relationships used by the tools, links entities back to products, and creates `chunk_embedding` and `chunkText` indexes.

### 4. Deploy The Agent

```bash
uv run python -m cli submit run_retail_agent_step1_deploy_agent.py
```

This logs the agent to MLflow, registers the model in Unity Catalog as `retail_assistant.retail.retail_graph_concierge`, deploys it with `databricks-agents`, and waits until the new model version is the active traffic target.

### 5. Verify Endpoint, Products, And Memory

```bash
uv run python -m cli submit run_retail_agent_step4_demo_agent.py
```

This checks endpoint readiness, runs diagnostics, exercises product search/detail/related-product tools, validates short-term memory, and validates long-term user preferences. It exits nonzero if the memory checks fail.

### 6. Demonstrate GraphRAG Retrievers

```bash
uv run python -m cli submit run_retail_agent_step5_demo_retrievers.py
```

This demonstrates:

| Retriever | Pattern |
|-----------|---------|
| `VectorRetriever` | Baseline semantic chunk search |
| `VectorCypherRetriever` | Vector search plus entity graph traversal |
| `HybridCypherRetriever` | Fulltext plus vector search plus entity traversal |
| `Text2CypherRetriever` | LLM-generated Cypher over the entity graph |

### 7. Verify Knowledge Tools Through The Endpoint

```bash
uv run python -m cli submit run_retail_agent_step6_check_knowledge.py
```

This sends live endpoint queries for troubleshooting, brand-specific hybrid search, product issue diagnosis, and cross-product knowledge comparison. It exits nonzero if the knowledge checks fail.

## Supervisor (stub)

The repository is structured for a future Mosaic AI multi-agent supervisor that routes analytics questions to a Genie space and product/KG questions to the deployed retail KG agent endpoint. The design is documented in [Agentic Commerce: GraphRAG Meets Agent Memory on Neo4j](docs/agentic-commerce.md). The implementation is a stub:

- `retail_agent/agent/supervisor.py` — skeleton with sub-agent specs, `build_supervisor_chat_agent()` that raises `NotImplementedError`, and the full TODO list in the module docstring.
- `retail_agent/step7_deploy_supervisor.py` — placeholder entry point. Submitting it via the runner prints a `STUB` banner and exits nonzero; it does not log, register, or deploy anything.
- `jobs/run_retail_agent_step7_deploy_supervisor.py` — matching job wrapper.
- `retail_agent/agent/config.py` — adds `supervisor_model_name` and `genie_space_id` fields. `genie_space_id` is empty by default and must be set before any real deployment.

To make this real, follow the TODOs in `retail_agent/agent/supervisor.py`: provision the Genie space, replace `build_supervisor_chat_agent()` with a real implementation using `databricks_ai_bridge.GenieAgent` and the multi-agent supervisor pattern, wire `step7_deploy_supervisor.py` to mirror `step1_deploy_agent.py`, and add a check script.

## Useful Runner Commands

```bash
# Show runner help
uv run python -m cli --help

# Validate cluster, workspace path, and uploaded jobs
uv run python -m cli validate

# Upload wrappers only
uv run python -m cli upload --all

# Build and upload the package wheel
uv run python -m cli upload --wheel

# Run a specific job wrapper
uv run python -m cli submit run_retail_agent_step4_demo_agent.py

# View Databricks job logs
uv run python -m cli logs <run-id>

# Smoke test remote execution
uv run python -m cli submit test_hello.py
```

## Local Validation

There are currently no pytest tests in this repository, so `uv run pytest` exits with code 5 after collecting 0 tests. Use these checks instead:

```bash
uv run python -m py_compile \
  retail_agent/step1_deploy_agent.py \
  retail_agent/step2_load_products.py \
  retail_agent/step3_load_graphrag.py \
  retail_agent/step4_demo_agent.py \
  retail_agent/step5_demo_retrievers.py \
  retail_agent/step6_check_knowledge.py \
  retail_agent/step7_deploy_supervisor.py \
  cli/__main__.py \
  jobs/_job_bootstrap.py

uv run python -m cli validate
```

## Optional Lakehouse Data Generation

The main agent runtime uses Neo4j. The repo also contains scripts for generating synthetic retail lakehouse data for Databricks SQL and Genie-style analytics demos.

Generate the expanded catalog data:

```bash
uv run python -m retail_agent.scripts.generate_transactions --expanded --verify
```

This writes CSVs to `data/lakehouse/`:

| File | Rows | Description |
|------|------|-------------|
| `transactions.csv` | ~1.15M | Line items across 500K orders |
| `customers.csv` | 5,000 | Customer dimension with segments |
| `reviews.csv` | ~115K | Product reviews linked to transactions |
| `inventory_snapshots.csv` | ~417K | Daily stock levels per product |
| `stores.csv` | 20 | Physical store locations |
| `knowledge_articles.csv` | Product knowledge articles | Product manuals, FAQs, and troubleshooting content |

Upload CSVs and create Delta tables:

```bash
uv run python -m retail_agent.scripts.lakehouse_tables
```

Options:

```bash
uv run python -m retail_agent.scripts.lakehouse_tables --skip-upload
uv run python -m retail_agent.scripts.lakehouse_tables --skip-tables
```

## Project Structure

```text
cli/
`-- __main__.py                       # databricks-job-runner entry point

jobs/
|-- _job_bootstrap.py                 # KEY=VALUE env injection + module runner
|-- test_hello.py                     # remote execution smoke test
|-- run_retail_agent_step1_deploy_agent.py
|-- run_retail_agent_step2_load_products.py
|-- run_retail_agent_step3_load_graphrag.py
|-- run_retail_agent_step4_demo_agent.py
|-- run_retail_agent_step5_demo_retrievers.py
|-- run_retail_agent_step6_check_knowledge.py
`-- run_retail_agent_step7_deploy_supervisor.py    # STUB

retail_agent/
|-- step1_deploy_agent.py             # compatibility wrapper
|-- step2_load_products.py            # compatibility wrapper
|-- step3_load_graphrag.py            # compatibility wrapper
|-- step4_demo_agent.py               # compatibility wrapper
|-- step5_demo_retrievers.py          # compatibility wrapper
|-- step6_check_knowledge.py          # compatibility wrapper
|-- step7_deploy_supervisor.py        # compatibility wrapper
|-- agent/
|   |-- serving.py                    # MLflow ChatAgent wrapper
|   |-- graph.py                      # LangGraph ReAct agent
|   |-- context.py                    # ToolRuntime context
|   |-- config.py                     # endpoint/model configuration
|   |-- demo_trace.py                 # structured demo trace extraction
|   `-- supervisor.py                 # multi-agent supervisor skeleton (STUB)
|-- tools/
|   |-- catalog.py
|   |-- knowledge.py
|   |-- memory.py
|   |-- preferences.py
|   |-- reasoning.py
|   |-- commerce.py
|   `-- diagnostics.py
|-- integrations/
|   |-- databricks/
|   |   |-- embeddings.py
|   |   |-- graphrag.py
|   |   `-- endpoint_client.py
|   `-- neo4j/
|       `-- memory_helpers.py
|-- deployment/
|   |-- deploy_agent.py
|   |-- deploy_supervisor.py
|   |-- load_products.py
|   `-- load_graphrag.py
|-- demos/
|   |-- demo_agent.py
|   |-- demo_retrievers.py
|   `-- check_knowledge.py
|-- data/
|   |-- product_catalog.py
|   `-- product_knowledge.py
|-- scripts/
|   |-- generate_transactions.py
|   |-- lakehouse_tables.py
|   `-- setup_databricks_secrets.sh
```

## Latest Verified Flow

The full Databricks pipeline has been verified with:

| Check | Result |
|-------|--------|
| Product graph load | Success |
| GraphRAG load | 252 documents processed |
| Endpoint deploy | Model version 5 active |
| Endpoint and memory checks | 9 passed, 0 failed |
| Retriever demo | Success |
| Knowledge checks | 4 passed, 0 failed |

Use `uv run python -m cli logs <run-id>` after each submitted step to inspect the full Databricks task output.
