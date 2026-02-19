# FIXIT: Product Tools `args_schema` vs `ToolRuntime` Injection

## Status: VERIFIED LOCALLY

All fixes applied and passing 14/14 tests in `fixit_sandbox/`.

---

## The Bug

The three product tools in `dbx_agent/product_search.py` (`search_products`, `get_product_details`, `get_related_products`) fail at runtime because `runtime` is `None` when the tool executes. The memory tools in `dbx_agent/memory_tool.py` work fine.

## Root Cause

Two differences between the product tools and the working memory tools:

1. **Product tools use `args_schema=SomePydanticModel`** on the `@tool` decorator. When `args_schema` is provided, LangChain uses that Pydantic schema *exclusively* to parse incoming arguments. Since `runtime` is not a field in `SearchProductsInput` (nor should it be — it's injected infrastructure, not a user-facing argument), LangChain/LangGraph never sees the `ToolRuntime` type hint and skips injection entirely.

2. **Product tools default `runtime` to `None`** (`runtime: ToolRuntime[RetailContext] = None`). The memory tools declare it without a default (`runtime: ToolRuntime[RetailContext]`). The `= None` default means even when injection fails silently, the tool still gets called — just with `runtime=None`, causing `AttributeError: 'NoneType' object has no attribute 'context'`.

## Research Sources

**Source: [LangChain Tools Documentation](https://docs.langchain.com/oss/python/langchain/tools)**

The official docs show two ways to define tool schemas:

1. **Let LangChain infer from the function signature** (preferred when using `ToolRuntime`):
   ```python
   @tool
   def get_weather(city: str, runtime: ToolRuntime) -> str:
       """Get weather for a given city."""
       ...
   ```

2. **Provide explicit `args_schema`** (for advanced schema customization):
   ```python
   @tool(args_schema=WeatherInput)
   def get_weather(location: str, units: str = "celsius") -> str:
       ...
   ```

**Every single example in the official docs that uses `ToolRuntime` uses approach #1 — none of them combine `args_schema` with `ToolRuntime`.** The `runtime` parameter is documented as a **reserved argument name** that is "automatically injected and hidden from the LLM" — but only when LangChain controls the schema inference from the function signature.

When you provide `args_schema`, you're telling LangChain: "I'll define the schema myself." LangChain respects that and never inspects the function signature for `ToolRuntime` hints.

### How `ToolRuntime` Injection Works

From the docs:

> **`ToolRuntime`**: A unified parameter that provides tools access to state, context, store, streaming, config, and tool call ID. This replaces the older pattern of using separate `InjectedState`, `InjectedStore`, `get_runtime`, and `InjectedToolCallId` annotations. The runtime automatically provides these capabilities to your tool functions without you having to pass them explicitly or use global state.

The `runtime` parameter is:
- **Hidden from the LLM** — it does not appear in the tool's `tool_call_schema`
- **Automatically injected** by `ToolNode` / `create_react_agent` at execution time
- **Requires LangChain to see the type hint** in the function signature during schema inference

---

## The Fix (Applied)

### Change 1: Remove `args_schema` from all three `@tool` decorators

```python
# Before
@tool(args_schema=SearchProductsInput)
async def search_products(...)

# After
@tool
async def search_products(...)
```

### Change 2: Remove `= None` default from `runtime` parameters

This ensures that if injection ever fails, the error is immediate and obvious rather than a deferred `AttributeError`.

### Change 3: Remove Pydantic input classes

`SearchProductsInput`, `ProductDetailsInput`, and `RelatedProductsInput` were removed entirely since they no longer serve a purpose.

### Change 4: Add `*,` before `runtime` where needed (discovered during testing)

Python does not allow a non-default parameter after parameters with defaults. In `search_products` and `get_related_products`, `runtime` (no default) follows parameters like `limit=10`. The fix: make `runtime` keyword-only by placing `*,` before it. This is correct because LangGraph injects `runtime` by name, not by position.

```python
# SyntaxError — non-default after default
async def search_products(
    query: str,
    limit: int = 10,
    runtime: ToolRuntime[RetailContext],  # ERROR
) -> str:

# Fixed — keyword-only parameter
async def search_products(
    query: str,
    limit: int = 10,
    *,
    runtime: ToolRuntime[RetailContext],  # OK
) -> str:
```

`get_product_details` does not need `*,` because `product_id` has no default.

---

## Local Test Results

### Test Suite: `fixit_sandbox/`

Run with: `bash fixit_sandbox/run_tests.sh`

```
14 passed in 0.28s
```

### Test 1: Schema Inference (`test_schema_inference.py`) — 10/10 PASSED

Imports the actual product and memory tools from `dbx_agent/` and verifies:

| Tool | `runtime` hidden from LLM? | User-facing params correct? |
|---|---|---|
| `search_products` | PASS | PASS — `{query, category, brand, max_price, limit}` |
| `get_product_details` | PASS | PASS — `{product_id}` |
| `get_related_products` | PASS | PASS — `{product_id, relationship_type, limit}` |
| `remember_message` | PASS | PASS — `{content}` |
| `recall_memory` | PASS | PASS — `{}` (no user args) |

### Test 2: Runtime Injection (`test_runtime_injection.py`) — 4/4 PASSED

Builds a minimal LangGraph `StateGraph` with `context_schema=MockContext`, a fake LLM node, and a `ToolNode`. Verifies end-to-end that:

| Test | Description | Result |
|---|---|---|
| `test_schema_hides_runtime` | `tool_call_schema` excludes `runtime` | PASS |
| `test_injection_with_custom_context` | Tool receives `MockContext(user_id="alice")` | PASS |
| `test_injection_with_default_context` | Tool receives default `MockContext()` | PASS |
| `test_injection_no_user_args` | Tool with only `runtime` param (no user args) works | PASS |

---

## Summary Table

| Aspect | Before (broken) | After (fixed) |
|---|---|---|
| `@tool` decorator | `@tool(args_schema=...)` | `@tool` |
| Schema source | Explicit Pydantic model | Auto-inferred from signature |
| `runtime` default | `= None` (silent failure) | No default (loud failure) |
| `runtime` position | After defaulted params (SyntaxError) | Keyword-only via `*,` |
| Pydantic input classes | Present but misleading | Removed |
| `ToolRuntime` injection | Skipped (schema override) | Works correctly |

## Next Steps

- [ ] Redeploy to Databricks: `uv run python -m dbx_agent.deploy`
- [ ] Verify on endpoint: `uv run python -m dbx_agent.check_endpoint`
