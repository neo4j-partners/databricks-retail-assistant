# Prototype Plan: Incremental Databricks Agent Validation

This document describes a step-by-step prototype plan to validate the core concepts from `LANGCHAIN_AGENT.md` before committing to the full tool refactor. Each step builds on the previous one and has a clear pass/fail outcome.

---

## Step 1: Create the Prototype Directory — DONE

Create `backend/dbx_agent/` as the home for all prototype code. This directory is separate from the future `backend/databricks_agent/` described in `LANGCHAIN_AGENT.md` — it exists purely for validation and can be deleted once the full implementation begins.

Files created:

| File | Purpose | Status |
|------|---------|--------|
| `backend/dbx_agent/__init__.py` | Empty | Done |
| `backend/dbx_agent/agent.py` | LangGraph agent with one echo tool | Done |
| `backend/dbx_agent/serving.py` | `ChatAgent` shim for Model Serving | Done |
| `backend/dbx_agent/config.py` | Deployment config (ported from aircraft_analyst `config.py`) | Done |
| `backend/dbx_agent/deploy.py` | Log → Register → Deploy pipeline (ported from aircraft_analyst `deploy.py`) | Done |
| `backend/dbx_agent/test_endpoint.py` | Endpoint verification script | Done |

This mirrors the layout proposed in `LANGCHAIN_AGENT.md` under "Architecture" but with minimal content — just enough to prove the deployment pipeline works.

---

## Step 2: Deploy a Bare-Bones Agent to Databricks — DONE (code ready, deploy pending)

The goal is to validate the deployment pipeline end-to-end with zero external dependencies. No Neo4j, no `neo4j-agent-memory`, no OpenAI embeddings. Just a LangGraph `create_react_agent` with one trivial tool that returns a hardcoded string.

### What the agent looks like — Implemented

`backend/dbx_agent/agent.py` — A `create_prototype_agent()` function that builds a `create_react_agent` with a single `echo` tool. The echo tool takes a string and returns `"Echo: {message}"`. The LLM defaults to `ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")` — a Databricks-hosted model that requires no API keys.

### What the serving adapter looks like — Implemented

`backend/dbx_agent/serving.py` — A `PrototypeAgent(ChatAgent)` class with lazy init via `_ensure_initialized()`. The `predict()` method calls `agent.invoke()` (sync, not async), extracts the final AI message from LangGraph's output, and returns a `ChatAgentResponse`. No `asyncio.run()` bridge needed at this stage.

### Configuration — Implemented

`backend/dbx_agent/config.py` — `DeployConfig` dataclass ported from aircraft_analyst's `config.py` pattern with retail-specific defaults:
- Unity Catalog: `retail_assistant.retail.dbx_agent_prototype` (matches existing `lakehouse_tables.py` naming)
- LLM: `databricks-meta-llama-3-3-70b-instruct` (no API key needed)
- `get_environment_vars()` returns empty dict for Step 2 (no secrets)
- All settings overridable via `RETAIL_AGENT_*` environment variables

### Deployment — Implemented

`backend/dbx_agent/deploy.py` — Four-step pipeline ported from aircraft_analyst's `deploy.py`:

1. `mlflow.pyfunc.log_model()` with Models-from-Code pointing at `serving.py`, `agent.py` in `code_paths`
2. `mlflow.register_model()` to Unity Catalog
3. `agents.deploy()` with no secret-backed environment variables (none needed yet)
4. Poll until endpoint is `READY`

Run with: `uv run python -m backend.dbx_agent.deploy`

### Implementation notes

- `serving.py` imports `agent.py` as `from agent import ...` (not `from backend.dbx_agent.agent import ...`) because MLflow's Models-from-Code loads `serving.py` directly with `code_paths` on `sys.path`. This matches the aircraft_analyst pattern where `mlflow_model.py` uses `from agent import ...`.
- `deploy.py` uses fully-qualified `from backend.dbx_agent.config import ...` because it runs as a normal module via `python -m`.
- `test_endpoint.py` uses `WorkspaceClient().serving_endpoints.query()` to send test messages.

### Pass criteria

- The endpoint reaches `READY` state
- A REST API call with a simple question gets a coherent response that uses the echo tool
- MLflow tracing shows the tool call in the trace

### What this proves

- The Models-from-Code pattern works with our project structure
- `create_react_agent` + `ChatAgent` shim deploys successfully
- The `agents.deploy()` pipeline from `LANGCHAIN_AGENT.md` is correct
- We can iterate on the agent without waiting for Neo4j setup

---

## Step 3: Add `neo4j-agent-memory` and Validate ToolRuntime — DONE (code ready, deploy pending)

Once Step 2 passes, add the memory library and validate two things simultaneously: that the wheel packaging from `MEMORY_LIBRARY.md` works in Model Serving, and that the `ToolRuntime` injection pattern from `LANGCHAIN_AGENT.md` works in practice.

### Files created/modified

| File | Purpose | Status |
|------|---------|--------|
| `backend/dbx_agent/context.py` | `RetailContext` dataclass (MemoryClient + session_id) | Done |
| `backend/dbx_agent/memory_tool.py` | `remember_message` + `recall_memory` tools with `ToolRuntime[RetailContext]` | Done |
| `backend/dbx_agent/agent.py` | Updated: `context_schema=RetailContext`, includes memory tools | Done |
| `backend/dbx_agent/serving.py` | Updated: lazy MemoryClient, `asyncio.run()` bridge, context injection | Done |
| `backend/dbx_agent/config.py` | Updated: `get_environment_vars()` returns Neo4j secrets | Done |
| `backend/dbx_agent/deploy.py` | Updated: wheel in `code_paths`, new code files, expanded pip_requirements | Done |
| `backend/dbx_agent/test_local.py` | Local validation script (agent + memory + ToolRuntime) | Done |

### Import path correction

`ToolRuntime` lives in `langgraph.prebuilt` (not `langchain_core.tools` as originally documented in `LANGCHAIN_AGENT.md`). Verified with langgraph 1.0.8 / langchain-core 1.2.13. See the "Import Path Correction" section added to `LANGCHAIN_AGENT.md`.

### Packaging the wheel

Follow `MEMORY_LIBRARY.md` Part 1 to build the wheel from the `maf` branch of `/Users/ryanknight/projects/neo4j-labs/agent-memory`:

```
cd ../agent-memory && make build
```

Then follow `MEMORY_LIBRARY.md` Part 3 to bundle it via `code_paths` in the `mlflow.langchain.log_model()` call. The wheel gets copied into the MLflow artifact and installed automatically at serving time.

### What to extract from the memory library

The simplest meaningful interaction with `neo4j-agent-memory` that proves the integration works is **short-term memory**: store a message, retrieve it. This exercises the Neo4j connection, the async driver, and the core `MemoryClient` API without requiring embeddings or entity extraction.

The `search_memory` tool in `backend/tools/memory_tools.py` is the closest existing example, but it uses `Neo4jMemoryRetriever` and embeddings. For the prototype, something even simpler is better — a tool that:

1. Calls `client.short_term.add_message(session_id, "user", content, extract_entities=False, generate_embedding=False)` to store a message
2. Calls `client.short_term.get_conversation(session_id)` to retrieve it
3. Returns the conversation as a string

This uses only the core `MemoryClient` API (see the `basic_usage.py` example in the agent-memory project) and requires only Neo4j — no OpenAI key, no embedding model.

### Introducing ToolRuntime

This is where we validate the `ToolRuntime[RetailContext]` pattern from `LANGCHAIN_AGENT.md` Section 2. The prototype tool declares a `runtime: ToolRuntime[RetailContext]` parameter and accesses `runtime.context.client` to get the `MemoryClient`, exactly as shown in the proposal.

The `RetailContext` dataclass from `LANGCHAIN_AGENT.md` Section 1 holds just the `MemoryClient` and `session_id`. The agent is built with `context_schema=RetailContext` as shown in Section 4.

**Important caveat**: `LANGCHAIN_AGENT.md` documents active LangGraph bugs (#6318, #6431) where `ToolRuntime` injection fails in `ToolNode` with Pydantic validation errors. If this happens, the fallback is `InjectedToolArg` — the tool uses `Annotated[RetailContext, InjectedToolArg]` instead of `ToolRuntime[RetailContext]`. This is the main reason we prototype before committing to the full 15-tool refactor.

### Serving adapter changes

The `ChatAgent` shim now needs:

1. **Lazy initialization** — `MemoryClient` cannot be created at import time because secrets are not available during `log_model()`. Follow the pattern from `LANGCHAIN_AGENT.md` Section 6: `_ensure_initialized()` creates the client on first `predict()` call.
2. **`asyncio.run()` bridge** — `MemoryClient` is async-only (see `LANGCHAIN_AGENT.md` "Async Tools in Model Serving" section). The sync `predict()` delegates to an async `_async_predict()` via `asyncio.run()`, which calls `agent.ainvoke()`.
3. **Secrets** — `NEO4J_URI` and `NEO4J_PASSWORD` are provisioned via `{{secrets/retail-agent-secrets/neo4j-uri}}` and `{{secrets/retail-agent-secrets/neo4j-password}}` as described in `LANGCHAIN_AGENT.md` Section 7.

### Databricks secrets setup

Before deploying, create the secret scope and store Neo4j credentials following `LANGCHAIN_AGENT.md` "Secrets Setup":

```
databricks secrets create-scope retail-agent-secrets
databricks secrets put-secret retail-agent-secrets neo4j-uri --string-value "neo4j+s://..."
databricks secrets put-secret retail-agent-secrets neo4j-password --string-value "..."
```

### Pass criteria

- The wheel installs successfully in the serving container (no import errors)
- The tool can store and retrieve a message via `MemoryClient.short_term`
- `ToolRuntime` (or the `InjectedToolArg` fallback) successfully injects the context
- The `asyncio.run()` bridge works — no event loop conflicts
- MLflow tracing shows the tool call with the memory interaction

### What this proves

- `neo4j-agent-memory` wheel packaging per `MEMORY_LIBRARY.md` works in Model Serving
- The async-only library works behind the `asyncio.run()` bridge
- `ToolRuntime` injection (or fallback) works in practice — safe to proceed with the full 15-tool refactor
- Secrets provisioning works for Neo4j credentials

---

## Step 4: Testing Strategy

Each step has its own testing approach, from local to deployed.

### Local testing (all steps)

Run the agent directly without Databricks. For Step 2, this is just `agent.invoke()` with a test message. For Step 3, this requires a Neo4j instance (local Docker or the Aura instance) and looks like:

```
uv run python -m backend.dbx_agent.test_local
```

This script creates a `RetailContext` with a local `MemoryClient`, invokes the agent with a test question, and prints the result. It validates that the agent, tools, and memory library work together before involving Databricks at all.

### Deployment testing (Step 2 and 3)

After `deploy.py` completes and the endpoint is `READY`, run a test script similar to `LANGCHAIN_AGENT.md` "Testing" section:

```
uv run python -m backend.dbx_agent.test_endpoint
```

This script:

1. Verifies the endpoint exists via `WorkspaceClient().serving_endpoints.get()`
2. Sends a test question via the REST API
3. Checks the response is coherent and includes tool usage
4. For Step 3: verifies the memory interaction actually persisted by sending a follow-up query

### Validating ToolRuntime specifically (Step 3)

The key validation is whether the injected `runtime.context.client` is the same `MemoryClient` instance that was constructed in `_ensure_initialized()`. The test script should:

1. Send a message that triggers the memory tool (e.g., "Remember that my name is Alex")
2. Send a second message in a new request (e.g., "What do you remember?")
3. Verify the second response references the stored information

If ToolRuntime injection is broken (the LangGraph bugs), the tool will fail with a Pydantic validation error. The test script should catch this cleanly and report which fallback to use.

### What to do if things fail

| Failure | Action |
|---------|--------|
| Models-from-Code import error | Check `code_paths` includes all needed modules; verify import paths use `backend.` prefix |
| Wheel install fails in serving | Check wheel is in `code_paths` and referenced in `extra_pip_requirements` per `MEMORY_LIBRARY.md` Part 3 |
| `ToolRuntime` Pydantic error | Switch to `InjectedToolArg` fallback documented in `LANGCHAIN_AGENT.md` Open Question 4 |
| `asyncio.run()` "event loop already running" | The serving container may already have a running loop; switch to `asyncio.get_event_loop().run_until_complete()` or `nest_asyncio` |
| Neo4j connection timeout | Verify secrets are correct; check that Aura instance allows connections from Databricks IP range |
| Agent returns no tool calls | Check the system prompt instructs the LLM to use the tool; verify tool schema is visible in the agent's tool list |

---

## Summary

| Step | What it validates | External deps | Estimated complexity |
|------|-------------------|---------------|---------------------|
| 1 | Directory structure | None | Trivial |
| 2 | Deployment pipeline, Models-from-Code, `ChatAgent` shim | Databricks only | Small — one dummy tool, no secrets |
| 3 | Wheel packaging, async bridge, `ToolRuntime` injection, Neo4j connection | Databricks + Neo4j | Medium — adds secrets, async, memory library |
| 4 | End-to-end validation | All of the above | Test scripts only |

Each step is independently deployable. If Step 2 fails, we debug the deployment pipeline before adding complexity. If Step 3 fails on `ToolRuntime`, we know to use the fallback before touching the 15 production tools. The prototype directory (`backend/dbx_agent/`) can be deleted once the findings are applied to the real implementation in `backend/databricks_agent/`.
