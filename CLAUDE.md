# Retail Assistant Project

## Directory Structure

- `backend/tools/` — LangChain tools for the **local FastAPI backend**. Uses closure factories (`create_tools(client)`) that close over a `MemoryClient`.
- `backend/dbx_agent/` — **Databricks-only** agent package. Uses `ToolRuntime[RetailContext]` dependency injection instead of closures. Deployed to Databricks Model Serving via MLflow and `agents.deploy()`. This code runs on Databricks, not locally.
- `backend/scripts/` — Data loading and generation scripts (Neo4j loader, transaction generator, lakehouse tables).

## backend/dbx_agent/ — Databricks Agent

This package is designed to run on Databricks Model Serving. Key constraints:

- **No `test_` prefixed files** — Databricks auto-discovers and runs them as pytest. Use names like `check_endpoint.py` instead. See `DBX_BEST_PRACTICES.md`.
- **Relative imports** — Files use `from context import RetailContext` (not `from backend.dbx_agent.context`), because MLflow packages them flat via `code_paths`.
- **Async bridging** — Uses a persistent background event loop, never `asyncio.run()`. See `DBX_BEST_PRACTICES.md`.
- **Deploy**: `uv run python -m backend.dbx_agent.deploy`
- **Check**: `uv run python -m backend.dbx_agent.check_endpoint`

## Running Scripts

Use `uv run` — the project venv is not auto-activated:

```
uv run python -m backend.scripts.<name>
uv run python -m backend.dbx_agent.deploy
uv run python -m backend.dbx_agent.check_endpoint
```
