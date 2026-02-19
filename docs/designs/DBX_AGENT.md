# dbx_agent/ — What's Been Built

## Overview

The `dbx_agent/` package is a Databricks-deployable Neo4j Knowledge Graph agent — the first of two sub-agents described in AGENTS.md. It runs as a Model Serving endpoint on Databricks, backed by the Llama 3.3 70B Instruct model and a Neo4j Aura knowledge graph. The package implements the `ToolRuntime[RetailContext]` dependency injection pattern from LANGCHAIN_AGENT.md, replacing the closure factories used in the local FastAPI backend.

## Architecture

The agent is a LangGraph `create_react_agent` wrapped in a thin MLflow `ChatAgent` adapter for Databricks Model Serving compatibility. All tools are async and use `ToolRuntime[RetailContext]` for dependency injection — the same tool objects can run in any environment by swapping the context. The serving adapter bridges sync Model Serving calls to async tool execution via a persistent background event loop running in a daemon thread.

## Components

### RetailContext (`context.py`)

A dataclass holding the `MemoryClient` and an optional `session_id`. This is the single dependency contract for all tools — LangGraph injects it automatically at invocation time via the `ToolRuntime` type hint.

### Tools

Three tool modules have been implemented, all using `ToolRuntime[RetailContext]` injection instead of closure factories:

- **Product Search** (`product_search.py`) — Three tools: `search_products` (vector similarity search with text fallback, plus optional category/brand/price filters), `get_product_details` (full product info by ID), and `get_related_products` (graph traversal across category, brand, and attribute relationships). Cypher queries are identical to the local backend versions.

- **Memory** (`memory_tool.py`) — Three tools: `remember_message` (stores messages in neo4j-agent-memory short-term memory), `recall_memory` (retrieves full conversation history for a session), and `search_memory` (semantic similarity search using `Neo4jMemoryRetriever`).

- **Diagnostics** (`diagnostics_tool.py`) — One tool: `agent_diagnostics` reports library versions, client connection status, capability flags, tool injection state, and the async bridging strategy. Used by `check_endpoint.py` to verify correct deployment.

There is also a baseline `echo` tool defined inline in `agent.py` for sanity-check validation.

### Embedder (`embedder.py`)

A custom `DatabricksEmbedder` class that implements the neo4j-agent-memory `Embedder` protocol using the Databricks Foundation Model API (`databricks-bge-large-en`, 1024 dimensions). It calls `mlflow.deployments.predict()` under the hood and includes endpoint validation at startup. This replaces the OpenAI embedder used in the local backend.

### Agent (`agent.py`)

Assembles all tools into a flat `ALL_TOOLS` list and builds the LangGraph ReAct agent with `create_react_agent(model, tools, prompt, context_schema=RetailContext)`. No singleton, no lazy init — the agent graph is a pure function of its inputs.

### Serving Adapter (`serving.py`)

A `ChatAgent` subclass that bridges Databricks Model Serving (sync `predict()`) to the async LangGraph agent. Key design decisions:

- Lazy initialization — secrets are only available at serving time, not during `log_model()`, so the `MemoryClient`, embedder, and agent are created on first request.
- Persistent background event loop — a daemon thread runs `loop.run_forever()` and all async work is dispatched via `run_coroutine_threadsafe()`. This avoids the "async driver bound to wrong event loop" problem that occurs with `asyncio.run()`.
- Session ID extraction from `custom_inputs` for multi-turn memory conversations.

### Configuration (`config.py`)

A `DeployConfig` dataclass with environment variable overrides (`RETAIL_AGENT_<SETTING>`). Covers Unity Catalog naming (`retail_assistant.retail.dbx_agent_prototype`), Databricks secret scope and key names, LLM endpoint, embedding model, scale-to-zero, and sample test queries.

### Deployment (`deploy.py`)

A four-step pipeline ported from the aircraft_analyst reference project: log model to MLflow (Models from Code pointing at `serving.py`, with tool modules and the neo4j-agent-memory wheel as `code_paths`), register to Unity Catalog, deploy via `agents.deploy()` with secret-backed environment variables, and wait for the endpoint to reach READY state. Supports a DELETE mode for teardown.

### Endpoint Verification (`check_endpoint.py`)

Sends raw REST calls to the deployed endpoint. Runs diagnostics, fires sample queries from the config, and exercises memory with a multi-turn scripted conversation (store facts, recall history, semantic search, context-based recommendations). Reports pass/fail for each memory turn.

### Data Loader (`load_products.py`)

Loads the 16-product sample catalog into Neo4j Aura using credentials from Databricks secrets. Creates Product, Category, Brand, and Attribute nodes with all relationships (IN_CATEGORY, MADE_BY, SIMILAR_TO, BOUGHT_TOGETHER, HAS_ATTRIBUTE). Generates product embeddings using the Databricks BGE model and creates the vector index. Also drops stale agent-memory vector indexes so they get recreated at the correct embedding dimensions.

## Current State

The Neo4j KG Agent is deployed and functional as a standalone Databricks Model Serving endpoint. It handles product search (vector and text), product details, related product discovery, conversation memory (store/recall/search), and diagnostics. It has been validated end-to-end via `check_endpoint.py`.

---

# What Remains

The following work from AGENTS.md has not been started.

## Remaining Tools (AGENTS.md R2 / LANGCHAIN_AGENT.md)

The local backend has 15 tools. The deployed agent has 7 (plus echo). The missing tools are:

- **Recommendations** — `get_recommendations`, `get_bought_together`, `explain_product_connection`
- **Inventory** — `check_inventory`, `find_alternatives`
- **Cart** — `get_cart`, `add_to_cart`, `remove_from_cart`, `update_cart_item`, `clear_cart`, `apply_coupon`

These need to be migrated from `backend/tools/` to `dbx_agent/` using the same `ToolRuntime[RetailContext]` pattern already established.

## Genie Space and Genie Agent (AGENTS.md R1)

No Genie Space has been created. The lakehouse tables (`retail_assistant.retail.transactions`, `transaction_items`, `products`, `customers`) exist in Unity Catalog, but there is no Genie Space connecting them with table/column descriptions, example queries, or synonyms. The `GenieAgent` wrapper has not been built.

## Multi-Agent Supervisor (AGENTS.md R3)

The LangGraph supervisor that routes between the Neo4j KG Agent and the Genie Agent does not exist. This includes the intent classifier, conditional routing logic, combined-query handling, and the supervisor's own `ChatAgent` adapter.

## MLflow Registration and Deployment of Supervisor (AGENTS.md R4)

The supervisor has not been logged, registered, or deployed. The current deployment is the standalone Neo4j KG Agent, not the multi-agent supervisor described in AGENTS.md.

## Evaluation (AGENTS.md R5)

No evaluation suite exists. No test questions have been curated and no baseline metrics have been established using Mosaic AI Agent Evaluation.

---

# Plan to Finish

### Step 1: Migrate Remaining Tools

Port the recommendations, inventory, and cart tools from `backend/tools/` to `dbx_agent/`. Follow the established pattern: replace closure over `client` with `ToolRuntime[RetailContext]`, export a flat tool list from each module, and add them to `ALL_TOOLS` in `agent.py`. Redeploy and verify with `check_endpoint.py`.

### Step 2: Create the Genie Space

In the Databricks workspace, create a Genie Space over the four retail Delta tables. Add table and column descriptions, example SQL queries for common analytics (revenue by period, top products, customer cohorts, basket analysis), business term synonyms, and scoping instructions. Test interactively until Genie generates accurate SQL for representative questions.

### Step 3: Build the Genie Agent Wrapper

Create a `GenieAgent` from `databricks-langchain` pointed at the Genie Space. Validate it programmatically by sending analytics questions and confirming it returns correct results.

### Step 4: Build the Supervisor

Create a LangGraph `StateGraph` supervisor that routes user queries to the Neo4j KG Agent, the Genie Agent, or both. Implement the LLM-based intent classifier and the combined-query synthesis path. Wrap the supervisor in a `ChatAgent` adapter and test end-to-end locally (or in a notebook).

### Step 5: Deploy the Supervisor

Log the supervisor with MLflow (declaring all resource dependencies: LLM endpoint, Genie Space, SQL warehouse). Register in Unity Catalog. Deploy via `agents.deploy()`. Verify the endpoint, Review App, and tracing.

### Step 6: Evaluation

Curate test questions spanning both agents and cross-agent reasoning. Run Mosaic AI Agent Evaluation and establish baseline quality metrics.
