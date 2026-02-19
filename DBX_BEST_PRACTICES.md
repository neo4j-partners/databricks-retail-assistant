# Databricks Best Practices

## File Naming: Avoid `test_` Prefix

**Do not name files with a `test_` or `test` prefix** (e.g., `test_local.py`, `test_endpoint.py`). Databricks automatically discovers and tries to run these as pytest test files, not as normal Python applications. This causes confusing failures when the file is a CLI script, not a test suite.

**Instead**, use descriptive names like `check_endpoint.py`, `validate_local.py`, or `run_smoke.py`.

---

## Keep `code_paths` in Sync with Imports

### The Problem

Adding a new file to `dbx_agent/` (e.g., `diagnostics_tool.py`) and importing it from `agent.py` caused the deploy to fail with: *"Model server failed to load the model."* No useful error details were shown in the UI.

### Root Cause

MLflow packages the agent using `code_paths` in `deploy.py`. Files listed in `code_paths` are copied into the model artifact and added to `sys.path` at serving time. If a file is imported by `agent.py` but **not listed in `code_files`**, the import fails with `ModuleNotFoundError` during model loading.

Because `dbx_agent/` uses **relative imports** (e.g., `from diagnostics_tool import ...`) for MLflow's flat packaging, there's no automatic discovery — every imported module must be explicitly listed.

### The Fix

When adding a new `.py` file to `dbx_agent/` that is imported at runtime, add it to the `code_files` list in `deploy.py`:

```python
code_files = [
    str(pkg_dir / "agent.py"),
    str(pkg_dir / "context.py"),
    str(pkg_dir / "diagnostics_tool.py"),  # <-- new file
    str(pkg_dir / "memory_tool.py"),
    str(pkg_dir / "product_search.py"),
]
```

### Checklist

When adding a new module to `dbx_agent/`:

1. Create the file with relative imports (e.g., `from context import RetailContext`)
2. Import it from `agent.py` or another packaged file
3. **Add it to `code_files` in `deploy.py`** — this is the step that's easy to forget
4. Files only used locally (e.g., `deploy.py`, `check_endpoint.py`, `config.py`) do **not** need to be in `code_files` — only files imported by `serving.py` or its import chain

---

## Async Event Loop in Model Serving

### The Problem

The prototype agent deployed to Databricks Model Serving worked for single requests but failed on subsequent requests that used async memory tools. The error was a truncated `StructuredTool._arun()` task pending error — an async task trying to use a Neo4j driver bound to a dead event loop.

### Root Cause

`serving.py` used `asyncio.run()` to bridge the sync `predict()` method (required by Databricks `ChatAgent`) to the async `_async_predict()` method. The issue:

1. **Request 1**: `asyncio.run()` creates **event loop A** → `MemoryClient.connect()` binds the Neo4j async driver to loop A → request completes → `asyncio.run()` **destroys loop A**
2. **Request 2**: `asyncio.run()` creates **event loop B** → `MemoryClient.is_connected` returns `True` (from request 1) so `connect()` is skipped → memory tool tries to use Neo4j driver still bound to **dead loop A** → crash

This is the classic "async driver bound to wrong event loop" problem. `asyncio.run()` creates a fresh event loop per call and destroys it on return. Any async resource (like Neo4j's `AsyncDriver`) that was created on the first loop becomes unusable on the second.

### Symptom

- First request with an async tool (e.g., `remember_message`) succeeded
- Second request with an async tool (e.g., `recall_memory`) failed with HTTP 400
- Sync tools (e.g., `echo`) always worked regardless of request order

### The Fix

Replaced `asyncio.run()` with a **persistent event loop running in a background thread**. All async work is dispatched to this loop via `asyncio.run_coroutine_threadsafe()`.

#### Before (broken)

```python
def predict(self, messages, context=None, custom_inputs=None):
    self._ensure_initialized()
    # Each call creates and destroys a new event loop
    return asyncio.run(self._async_predict(messages, context, custom_inputs))

async def _async_predict(self, messages, context, custom_inputs):
    # Connect on first call — binds driver to THIS loop
    if self._client and not self._client.is_connected:
        await self._client.connect()
    # ... invoke agent
```

#### After (fixed)

```python
def _create_background_loop() -> asyncio.AbstractEventLoop:
    """One loop, one thread, lives forever."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()),
        daemon=True,
    )
    thread.start()
    return loop

class PrototypeAgent(ChatAgent):
    def _ensure_initialized(self):
        # Create persistent loop and connect client on it at init time
        self._loop = _create_background_loop()
        self._client = MemoryClient(settings)
        future = asyncio.run_coroutine_threadsafe(self._client.connect(), self._loop)
        future.result(timeout=30)

    def predict(self, messages, context=None, custom_inputs=None):
        self._ensure_initialized()
        # Every request runs on the SAME loop the driver was connected on
        future = asyncio.run_coroutine_threadsafe(
            self._async_predict(messages, context, custom_inputs),
            self._loop,
        )
        return future.result(timeout=120)
```

### Why This Works

- The Neo4j async driver is created and connected on the background loop
- That loop never dies (the daemon thread runs `loop.run_forever()`)
- Every subsequent request dispatches to the same loop
- `run_coroutine_threadsafe()` is thread-safe and returns a `concurrent.futures.Future` that blocks the calling thread until the coroutine completes

### What We Learned from the Agent Memory Library

The `neo4j-agent-memory` library at `/Users/ryanknight/projects/neo4j-labs/agent-memory` is **100% async**. There are no sync alternatives for any of the core APIs:

- `MemoryClient` uses `AsyncDriver` and `AsyncSession` from the Neo4j Python driver
- `ShortTermMemory` methods (`add_message`, `get_conversation`, `search_messages`) are all `async def`
- `MemoryClient.connect()` is async and must be awaited before any operations

The library does provide sync bridging utilities in `integrations/base.py`:

- A `run_sync` decorator that uses a shared `ThreadPoolExecutor` and calls `asyncio.run()` inside the thread
- A `_run_async` helper in the LangChain integration that uses `run_coroutine_threadsafe()` when already in an async context

However, the `run_sync` decorator still calls `asyncio.run()` per invocation (inside the thread), which would have the same loop-lifetime problem for long-lived connections. The persistent background loop approach avoids this entirely.

### Key Takeaway

When bridging async-only libraries into sync frameworks (like Databricks `ChatAgent.predict()`), **never use `asyncio.run()` if the async code holds long-lived resources** (database connections, drivers, sessions). Use a persistent event loop in a background thread instead. This ensures all async resources stay on the same loop for the lifetime of the process.

---

## Stale Deploys: Verifying What's Actually Running

### The Problem

After fixing the event loop bug locally and redeploying, product search tools still failed with HTTP 400 errors. The error message from the endpoint was truncated: `'NoneType' object has no ...` — which was misleading and sent debugging in the wrong direction (investigating which attribute was None).

### Root Cause

The deployed code was **stale**. The server logs (`server.logs`) revealed the actual error:

```
RuntimeError: Task <Task pending ...> got Future <Future pending> attached to a different loop
```

And critically, the traceback showed line 105 of the deployed `serving.py`:

```python
return asyncio.run(self._async_predict(messages, context, custom_inputs))
```

The deployed version was still using `asyncio.run()` — the old broken pattern — even though the local code had been updated to use the persistent background loop. The deploy had either failed silently or an older model version was still being served.

### Why It Was Confusing

- **Memory tools appeared to work** on the first few requests because they were the first async Neo4j calls on fresh gunicorn workers. Subsequent tool calls on the same worker hit the loop mismatch.
- **The HTTP 400 error message was truncated** by the endpoint, hiding the real `RuntimeError` and showing only `'NoneType' object has no` — which looked like a completely different bug (missing attribute on a None object).
- **The local code was correct**, making it seem like the fix should have worked.

### The Fix: Diagnostics Tool

Added a `diagnostics_tool.py` — a **sync** tool (no Neo4j, so immune to the loop bug) that reports environment info when queried:

```python
@tool
def agent_diagnostics(runtime: ToolRuntime[RetailContext]) -> str:
    """Return diagnostic information about the agent environment."""
    info = {}

    # Library version
    import neo4j_agent_memory
    info["neo4j_agent_memory_version"] = neo4j_agent_memory.__version__

    # Client status
    client = runtime.context.client
    info["has_graph"] = getattr(client, "_client", None) is not None
    info["has_embedder"] = getattr(client, "_embedder", None) is not None

    # Detect which async bridge pattern is deployed
    import importlib, inspect
    serving = importlib.import_module("serving")
    source = inspect.getsource(serving.PrototypeAgent.predict)
    if "run_coroutine_threadsafe" in source:
        info["async_bridge"] = "persistent_loop"
    elif "asyncio.run" in source:
        info["async_bridge"] = "asyncio_run"
    ...
```

The `async_bridge` field is the key diagnostic — it inspects the deployed `serving.py` source to confirm which async bridging pattern is actually running. Expected output after a correct deploy:

```json
{
  "neo4j_agent_memory_version": "0.1.0",
  "client_initialized": true,
  "has_graph": true,
  "has_embedder": true,
  "async_bridge": "persistent_loop"
}
```

If the deploy is stale, `async_bridge` will read `"asyncio_run"` — an immediate signal that the code hasn't been updated.

### Integration with check_endpoint.py

The diagnostics query runs **before** sample queries in `check_endpoint.py`. This way, if something is wrong with the deployed environment, you see it immediately without having to dig through server logs.

### Lessons Learned

1. **Databricks endpoint error messages are often truncated.** Always check `server.logs` for the full traceback — the truncated message can be misleading.
2. **Always verify the deployed code matches local code.** A diagnostics tool that inspects its own source is a reliable way to confirm what's actually running.
3. **Use sync diagnostics tools for debugging async issues.** A sync tool won't be affected by the very bug you're trying to diagnose.
4. **Run diagnostics first.** Putting the version/environment check before sample queries in `check_endpoint.py` saves significant debugging time.

---

## Server Logs: Always Check the Full Traceback

### The Problem

Databricks Model Serving returns truncated error messages in HTTP 400 responses. The message `'NoneType' object has no` was actually a truncation of a `RuntimeError` about event loop mismatches — a completely different class of error.

### How to Access Logs

Server logs are available on the endpoint's serving page in the Databricks workspace. Save them locally (e.g., `server.logs`) for easier analysis. The logs contain full Python tracebacks with file paths, line numbers, and the complete error message.

### Key Takeaway

When an endpoint returns a vague or truncated error, **never debug from the truncated message alone**. Always pull the server logs first to see the real exception and full stack trace.
