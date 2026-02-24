# Rules

- Always ask clarifying questions before making changes. Do not assume intent, scope, or approach — confirm with the user first.

# Retail Assistant Project

## Directory Structure

- `retail_agent/` — **Databricks-only** agent package. Uses `ToolRuntime[RetailContext]` dependency injection instead of closures. Deployed to Databricks Model Serving via MLflow and `agents.deploy()`. This code runs on Databricks, not locally.

## retail_agent/ — Databricks Agent

This package is designed to run on Databricks Model Serving. Entry-point scripts live at the top level; library code lives in `src/`.

### Layout

- `deploy.py` — Step 1: Deploy agent to Databricks Model Serving
- `load_products.py` — Step 3: Load sample product data into Neo4j
- `check_endpoint.py` — Steps 2 & 4: Verify deployment / run sample queries
- `src/` — Internal library (packaged flat via MLflow `code_paths`):
  - `serving_adapter.py` — MLflow ChatAgent adapter
  - `react_agent.py` — LangGraph ReAct agent definition
  - `deploy_config.py` — Deployment configuration (CONFIG singleton)
  - `retail_context.py` — RetailContext dataclass for DI
  - `diagnostics_tool.py` — Agent environment diagnostics
  - `databricks_embedder.py` — Databricks Foundation Model embedder
  - `memory_tools.py` — Memory tools (remember, recall, search)
  - `product_tools.py` — Product search/lookup/related tools
- `data/` — Product data definitions:
  - `product_catalog.py` — Product data definitions
  - `product_knowledge.py` — Knowledge articles, support tickets, reviews
- `scripts/` — Databricks data pipeline scripts:
  - `generate_transactions.py` — Generate 500K transaction CSVs for Delta Lake
  - `lakehouse_tables.py` — Upload CSVs to Databricks Unity Catalog

### Key constraints

- **No `test_` prefixed files** — Databricks auto-discovers and runs them as pytest. Use names like `check_endpoint.py` instead. See `RETAIL_BEST_PRACTICES.md`.
- **Relative imports in `src/`** — Files use `from retail_context import RetailContext` (not `from retail_agent.src.retail_context`), because MLflow packages them flat via `code_paths`.
- **Async bridging** — Uses a persistent background event loop, never `asyncio.run()`. See `RETAIL_BEST_PRACTICES.md`.
- **Deploy**: `uv run python -m retail_agent.deploy`
- **Check**: `uv run python -m retail_agent.check_endpoint`

## Running Scripts

Use `uv run` — the project venv is not auto-activated:

```
# Databricks agent
uv run python -m retail_agent.deploy
uv run python -m retail_agent.check_endpoint
uv run python -m retail_agent.load_products
uv run python -m retail_agent.scripts.generate_transactions
uv run python -m retail_agent.scripts.lakehouse_tables
```
