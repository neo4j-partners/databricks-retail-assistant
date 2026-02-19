# Async Event Loop Issue in Databricks Model Serving

## The Problem

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

## The Fix

Replaced `asyncio.run()` with a **persistent event loop running in a background thread**. All async work is dispatched to this loop via `asyncio.run_coroutine_threadsafe()`.

### Before (broken)

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

### After (fixed)

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

## What We Learned from the Agent Memory Library

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
