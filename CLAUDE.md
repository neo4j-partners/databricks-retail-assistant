# Rules

- Always ask clarifying questions before making changes. Do not assume intent, scope, or approach — confirm with the user first.

# Retail Assistant Project

## Directory Structure

- `retail_agent/` — **Databricks-only** agent package. Uses `ToolRuntime[RetailContext]` dependency injection instead of closures. Deployed to Databricks Model Serving via MLflow and `agents.deploy()`. This code runs on Databricks, not locally.

## retail_agent/ — Databricks Agent

This package is designed to run on Databricks Model Serving. Top-level step scripts are compatibility wrappers; implementation code is organized by responsibility.

### Layout

- `step1_deploy_agent.py` — Deploy agent to Databricks Model Serving
- `step2_load_products.py` — Load sample product data into Neo4j
- `step3_load_graphrag.py` — Build GraphRAG layer on product knowledge graph
- `step4_demo_agent.py` — Verify deployment / run sample queries
- `step5_demo_retrievers.py` — Demo GraphRAG retriever patterns
- `agent/` — Core agent runtime:
  - `serving.py` — MLflow ChatAgent adapter
  - `graph.py` — LangGraph ReAct agent definition
  - `config.py` — Deployment configuration (CONFIG singleton)
  - `context.py` — RetailContext dataclass for DI
- `tools/` — Agent tools grouped by domain:
  - `catalog.py` — Product search/lookup/related tools
  - `knowledge.py` — GraphRAG search and diagnosis tools
  - `memory.py` — Memory tools (remember, recall, search)
  - `preferences.py` — Long-term preference tools
  - `reasoning.py` — Reasoning trace tools
  - `commerce.py` — Personalized recommendation tools
  - `diagnostics.py` — Agent environment diagnostics
- `integrations/` — Databricks and Neo4j helper modules:
  - `databricks/embeddings.py` — Foundation Model embedder
  - `databricks/graphrag.py` — neo4j-graphrag Databricks adapters
  - `databricks/endpoint_client.py` — Model Serving endpoint client
  - `neo4j/memory_helpers.py` — Neo4j memory helper functions
- `deployment/` and `demos/` — Implementation entry points behind the top-level step wrappers
- `data/` — Product data definitions:
  - `product_catalog.py` — Product data definitions
  - `product_knowledge.py` — Knowledge articles, support tickets, reviews
- `scripts/` — Databricks data pipeline scripts:
  - `generate_transactions.py` — Generate 500K transaction CSVs for Delta Lake
  - `lakehouse_tables.py` — Upload CSVs to Databricks Unity Catalog

### Key constraints

- **No `test_` prefixed files** — Databricks auto-discovers and runs them as pytest. Use names like `check_endpoint.py` instead. See `RETAIL_BEST_PRACTICES.md`.
- **Package imports** — Runtime modules use package-qualified imports under `retail_agent.*`; MLflow packages the `retail_agent` package via `code_paths`.
- **Async bridging** — Uses a persistent background event loop, never `asyncio.run()`. See `RETAIL_BEST_PRACTICES.md`.
- **Deploy**: Run `step1_deploy_agent.py` on Databricks cluster
- **Check**: Run `step4_demo_agent.py` on Databricks cluster

## Running Scripts

Step scripts run on a Databricks cluster (via Run button or Databricks Job):

- `step1_deploy_agent.py` — Deploy agent to Model Serving
- `step2_load_products.py` — Load product data into Neo4j
- `step3_load_graphrag.py` — Build GraphRAG layer
- `step4_demo_agent.py` — Demo basic agent capabilities
- `step5_demo_retrievers.py` — Demo GraphRAG retriever patterns
- `step6_check_knowledge.py` — Exercise GraphRAG knowledge tools

Local data pipeline scripts (run with `uv run`):

```
uv run python -m retail_agent.scripts.generate_transactions
uv run python -m retail_agent.scripts.lakehouse_tables
```
