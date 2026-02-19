# Embedding Plan for the Databricks Retail Agent

## Problem

The agent's `search_memory` tool does not work because embeddings are never generated or stored. The `remember_message` tool stores messages with embedding generation disabled, and the `MemoryClient` is created without any embedding provider. The `Neo4jMemoryRetriever` used by `search_memory` relies entirely on vector similarity search, so it silently returns empty results.

## Goal

Configure the Databricks agent to generate and store embeddings when messages are saved, so that semantic memory search works end to end.

## Reference Project

The embedding approach is based on the patterns established in the Databricks embedding test project at `/Users/ryanknight/projects/databricks/dbx-embedding-tests`. That project tests Databricks built-in and custom embedding models against Neo4j, measures throughput, and documents the API formats. The `DBX_EMBEDDING.md` file in that project summarizes the test results and model details.

## Databricks Built-in Model

The recommended model is `databricks-bge-large-en`. It is a Foundation Model API endpoint that is pre-deployed on every Databricks workspace — no setup or model serving endpoint required.

- 1024 dimensions
- 512 token context length
- Normalized output vectors
- OpenAI-compatible API format (send text in an `input` field, receive embeddings in a `data` array)

An alternative is `databricks-gte-large-en`, which has the same 1024 dimensions but supports 8192 token context. This is better for longer documents but is otherwise interchangeable.

## Custom Model Option

For teams that want smaller embeddings or a self-hosted model, a custom embedding endpoint can be deployed to Databricks Model Serving. The embedding test project demonstrates this with a MiniLM model (384 dimensions) registered to Unity Catalog and served via a custom endpoint. The API format for custom endpoints uses the `dataframe_records` format instead of the OpenAI-compatible format. The agent-memory library supports custom embedders through its `embedder` constructor parameter, so either approach works.

## Changes Required

### 1. Create a Databricks embedder class

The agent-memory library defines an `Embedder` protocol that any embedding provider must follow. It requires three things: a `dimensions` property that returns the vector size, an async `embed` method that takes a single string and returns a list of floats, and an async `embed_batch` method that takes a list of strings and returns a list of float lists.

A new file in `dbx_agent/` will implement this protocol by calling the Databricks Foundation Model API REST endpoint. The embedder will use the workspace URL and token already available in the serving environment to make HTTP calls to the built-in `databricks-bge-large-en` model. The call format is OpenAI-compatible: post a JSON body with an `input` field containing the text, and parse the embedding vectors from the response's `data` array.

The class should support batching since the Foundation Model API accepts multiple texts in a single request.

### 2. Pass the embedder to MemoryClient in serving.py

The `MemoryClient` constructor accepts an optional `embedder` parameter. When provided, it uses that embedder instead of trying to create one from the `EmbeddingConfig` settings. The `_ensure_initialized` method in `serving.py` will create an instance of the Databricks embedder and pass it when constructing the `MemoryClient`.

The embedder needs the workspace URL and an auth token. Inside a Databricks Model Serving container, the workspace URL comes from the `DATABRICKS_HOST` environment variable (or can be derived from the serving context), and the token comes from the default credentials available in the container.

### 3. Enable embedding generation in remember_message

The `remember_message` tool in `memory_tool.py` currently calls `add_message` with `generate_embedding=False`. This needs to change to `generate_embedding=True` so that every stored message gets an embedding vector. This is a one-line change.

### 4. Add the embedding endpoint name to secrets or config

The model name (`databricks-bge-large-en`) should be stored in `config.py` as a setting so it can be overridden. The dimensions (1024) should also be a config value. No new Databricks secrets are needed since the built-in model does not require an API key beyond the workspace auth.

### 5. Update the Neo4j vector index in load_products.py

The database is set up by running `uv run python -m backend.scripts.load_products`. That script currently creates a product vector index at 1536 dimensions and generates product embeddings using OpenAI. There are two separate vector concerns to address:

**Product embeddings** — The `_create_vector_index` function in `load_products.py` hardcodes 1536 dimensions for the `product_embedding` index on Product nodes. The `_generate_embeddings` function uses the OpenAI API to generate those embeddings. If we want the product search to also work on Databricks without requiring an OpenAI key, the script should be updated to support Databricks embeddings as an alternative. That means changing the hardcoded 1536 to a configurable dimension (1024 for Databricks BGE) and adding a Databricks embedding path alongside the existing OpenAI path in `_generate_embeddings`. The product search tool in `dbx_agent/product_search.py` would also need to generate query embeddings using the same Databricks model to match.

**Message embeddings** — The agent-memory library manages its own schema for message nodes and should create vector indexes during `MemoryClient.connect()`. However, the dimensions must match the embedder being used. Since we are passing a 1024-dimension Databricks embedder to the MemoryClient, the library should create its message vector index at 1024 dimensions automatically. If the database already has a message vector index from a previous run with different dimensions (for example 1536 from OpenAI), that index will need to be dropped first. The load_products script should add a step that drops any stale message embedding indexes so the agent-memory library can recreate them cleanly at the correct dimension.

## Implementation Status

1. **Create Databricks embedder class** — DONE
   - `dbx_agent/embedder.py` — `DatabricksEmbedder` class implementing the Embedder protocol
   - Uses httpx async client, calls `/serving-endpoints/{model}/invocations` with OpenAI-compatible format
   - Supports single and batch embedding

2. **Add embedding config to config.py** — DONE
   - `dbx_agent/config.py` — Added `embedding_model` (default `databricks-bge-large-en`) and `embedding_dimensions` (default 1024)
   - Env var overrides: `RETAIL_AGENT_EMBEDDING_MODEL`, `RETAIL_AGENT_EMBEDDING_DIMENSIONS`

3. **Wire embedder into serving.py** — DONE
   - `dbx_agent/serving.py` — Creates `DatabricksEmbedder` from workspace URL/token and passes as `embedder=` to `MemoryClient`
   - Falls back to `WorkspaceClient` SDK if env vars not set directly

4. **Enable embedding generation in remember_message** — DONE
   - `dbx_agent/memory_tool.py` — Flipped `generate_embedding=False` to `True`

5. **Update Neo4j vector index in load_products.py** — DONE
   - `backend/scripts/load_products.py` — `_create_vector_index` reads `EMBEDDING_DIMENSIONS` from settings instead of hardcoded 1536
   - Added `_drop_stale_message_indexes` to clean up agent-memory indexes with wrong dimensions
   - `backend/config.py` — Added `embedding_dimensions` setting (default 1536)
   - `.env.sample` — Added `EMBEDDING_DIMENSIONS` with documentation for OpenAI (1536) vs Databricks (1024) values

## Verification

After deploying, run `uv run python -m dbx_agent.check_endpoint`. The memory exercise Turn 4 ("Search your memory for anything about my shoe preferences") should return results instead of empty, confirming that embeddings are being generated, stored, and searched successfully.
