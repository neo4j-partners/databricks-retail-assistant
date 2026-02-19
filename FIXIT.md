# FIXIT: Product Tools `args_schema` vs `ToolRuntime` Injection

## The Bug

The three product tools in `dbx_agent/product_search.py` (`search_products`, `get_product_details`, `get_related_products`) fail at runtime because `runtime` is `None` when the tool executes. The memory tools in `dbx_agent/memory_tool.py` work fine.

## Root Cause

Two differences between the product tools and the working memory tools:

1. **Product tools use `args_schema=SomePydanticModel`** on the `@tool` decorator. When `args_schema` is provided, LangChain uses that Pydantic schema *exclusively* to parse incoming arguments. Since `runtime` is not a field in `SearchProductsInput` (nor should it be — it's injected infrastructure, not a user-facing argument), LangChain/LangGraph never sees the `ToolRuntime` type hint and skips injection entirely.

2. **Product tools default `runtime` to `None`** (`runtime: ToolRuntime[RetailContext] = None`). The memory tools declare it without a default (`runtime: ToolRuntime[RetailContext]`). The `= None` default means even when injection fails silently, the tool still gets called — just with `runtime=None`, causing `AttributeError: 'NoneType' object has no attribute 'context'`.

## Proposed Fix: Remove `args_schema=` from Product Tool Decorators

**Yes, this is the correct approach.** This is confirmed by official LangChain documentation and the LangGraph codebase patterns.

### Evidence from Official Docs

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
- **Hidden from the LLM** — it does not appear in the tool's schema sent to the model
- **Automatically injected** by `ToolNode` / `create_react_agent` at execution time
- **Requires LangChain to see the type hint** in the function signature during schema inference

### Why Memory Tools Work

`memory_tool.py` uses the correct pattern:

```python
@tool  # <-- No args_schema
async def remember_message(
    content: str,
    runtime: ToolRuntime[RetailContext],  # <-- No default
) -> str:
```

LangChain infers the schema from the function signature, sees `ToolRuntime`, hides it from the LLM schema, and injects it at runtime. The LLM only sees `content: str`.

### Why Product Tools Break

`product_search.py` uses the conflicting pattern:

```python
@tool(args_schema=SearchProductsInput)  # <-- Overrides schema inference
async def search_products(
    query: str,
    ...,
    runtime: ToolRuntime[RetailContext] = None,  # <-- Never seen by LangChain
) -> str:
```

LangChain uses `SearchProductsInput` exclusively. It never inspects the function signature, never finds the `ToolRuntime` hint, and never injects `runtime`.

## The Fix

### Step 1: Remove `args_schema` from all three `@tool` decorators

```python
# Before
@tool(args_schema=SearchProductsInput)
async def search_products(...)

# After
@tool
async def search_products(...)
```

### Step 2: Remove `= None` default from `runtime` parameters

```python
# Before
runtime: ToolRuntime[RetailContext] = None,

# After
runtime: ToolRuntime[RetailContext],
```

This ensures that if injection ever fails, the error is immediate and obvious rather than a deferred `AttributeError`.

### Step 3: Keep the Pydantic input classes (optional)

The `SearchProductsInput`, `ProductDetailsInput`, and `RelatedProductsInput` classes can remain in the file as documentation. They just won't be passed to `@tool` anymore. LangChain will auto-generate an equivalent schema from the function parameters, their type hints, and `Field()` descriptions.

To preserve the `Field(ge=0)` / `Field(ge=1, le=50)` validators that Pydantic provides, add `Annotated` hints to the function parameters:

```python
from typing import Annotated
from pydantic import Field

@tool
async def search_products(
    query: str = Field(description="Search query describing what the customer is looking for"),
    category: str | None = Field(default=None, description="Filter by product category"),
    brand: str | None = Field(default=None, description="Filter by brand name"),
    max_price: Annotated[float | None, Field(default=None, ge=0, description="Maximum price filter")] = None,
    limit: Annotated[int, Field(default=10, ge=1, le=50, description="Maximum number of results")] = 10,
    runtime: ToolRuntime[RetailContext],
) -> str:
```

Or, if the validators aren't critical for the LLM-facing schema (the LLM doesn't enforce `ge`/`le` anyway), simply rely on type hints and the docstring:

```python
@tool
async def search_products(
    query: str,
    category: str | None = None,
    brand: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
    runtime: ToolRuntime[RetailContext],
) -> str:
    """Search the product catalog by query. ..."""
```

## Summary

| Aspect | Product Tools (broken) | Memory Tools (working) |
|---|---|---|
| `@tool` decorator | `@tool(args_schema=...)` | `@tool` |
| Schema source | Explicit Pydantic model | Auto-inferred from signature |
| `runtime` default | `= None` (silent failure) | No default (loud failure) |
| `ToolRuntime` injection | Skipped (schema override) | Works correctly |

**Recommendation: Remove `args_schema=` and `= None` default. This is the canonical pattern shown in all official LangChain/LangGraph documentation for tools that use `ToolRuntime` injection.**
