# Tool Sandbox — Debugging ToolRuntime Injection

## Problem Summary

Product search tools fail in production with `AttributeError: 'NoneType' object has no attribute 'context'` — meaning `runtime` is `None`. Memory tools and diagnostics tool work fine. All deployed on Databricks Model Serving with `langchain-core==1.2.13`, `langgraph==1.0.8`.

## Key Differences Between Working and Broken Tools

| Aspect | Memory Tools (work) | Product Tools (broken) |
|---|---|---|
| `args_schema` | Not used | `@tool(args_schema=SearchProductsInput)` |
| `runtime` default | No default | `= None` |
| async | `async def` | `async def` |

## Research Findings

### args_schema + ToolRuntime

- Known bug in older langchain-core (GitHub #33646, #34293, #34246)
- Fixed in PR #33999 (Nov 2025), present in langchain-core 1.2.13
- Local testing confirms injection works with both `args_schema` and without

### The Untested Variable: Persistent Background Loop

The deployed serving.py uses `run_coroutine_threadsafe()` to dispatch `agent.ainvoke()` onto a persistent background event loop. Hypothesis was this could interfere with context propagation.

**Result: NOT the cause.** Test 3 reproduces this exact pattern locally and it passes.

### What We Can't Reproduce Locally

- Gunicorn sync worker process model (4 workers, PIDs 13-16 in server.logs)
- MLflow's ChatAgent wrapper (`mlflow.pyfunc.loaders.chat_agent`)
- The exact dependency resolution on the Databricks runtime

## Test Results

| Test | Status | Result |
|---|---|---|
| Test 1: Direct ainvoke | PASSED | All 4 tool patterns inject runtime correctly |
| Test 2: Full agent (asyncio.run) | PASSED | All 4 tool patterns work through create_react_agent |
| Test 3: run_coroutine_threadsafe | PASSED | All 4 tool patterns work with persistent background loop |

## Conclusion

**The bug is NOT reproducible locally** with `langchain-core==1.2.13` and `langgraph==1.0.8`. All tool patterns (with/without `args_schema`, with/without default on `runtime`) work correctly through all dispatch mechanisms.

## Next Steps — On-Cluster Debugging

Since the bug only manifests in the Databricks serving container, the next step is to add instrumentation to the deployed agent that captures:

1. **Actual installed versions** at runtime (via `diagnostics_tool`)
2. **The `_injected_args` dict** from the ToolNode — does it detect `runtime` for product tools in the container?
3. **The `_injected_args_keys` set** from each tool — does langchain-core's detection work in the container?

### Proposed Fix: Remove args_schema (safest)

Even though the bug doesn't reproduce locally, the safest fix is to **remove `args_schema=` from product tools** and rely on LangChain's schema inference from function signatures. This eliminates the only variable that differs between working and broken tools.

This is Pattern A from the LangChain docs — the recommended approach when using `ToolRuntime`:

```python
# Before (Pattern B — with args_schema)
@tool(args_schema=SearchProductsInput)
async def search_products(query: str, ..., runtime: ToolRuntime[RetailContext] = None):

# After (Pattern A — inferred schema)
@tool
async def search_products(query: str, ..., runtime: ToolRuntime[RetailContext] = None):
```

The Pydantic `Field()` descriptions can be moved to `Annotated` type hints if needed.
