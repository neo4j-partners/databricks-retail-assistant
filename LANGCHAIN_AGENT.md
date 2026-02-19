# R2: Neo4j KG Agent for Databricks

This document proposes the implementation of the Neo4j Knowledge Graph Agent as a Databricks-compatible agent. The deployment pipeline (MLflow log → Unity Catalog register → `agents.deploy()`) follows the pattern proven in the [aircraft_analyst](../aircraft_analyst/) project (see `DATABRICKS_AGENT.md`), but the tool architecture uses LangGraph's `ToolRuntime` injection instead of the closure + singleton pattern used there.

## Problem

The retail assistant has 15 LangChain tools (product search, recommendations, cart, inventory, memory) backed by a Neo4j knowledge graph, but they only run inside the local FastAPI backend. To participate in the multi-agent supervisor on Databricks (AGENTS.md R3–R5), the tools need to be wrapped in a LangGraph agent that conforms to Databricks Model Serving requirements.

The current `create_tools(client: MemoryClient)` closure factory bakes the Neo4j connection in at tool creation time. This creates portability problems:

- Running the same tools with a different client (local vs Databricks) means rebuilding every tool
- Closures cannot be serialized by MLflow — the Models-from-Code workaround re-executes the entire module, forcing tool construction into the module's top level
- Testing requires mocking at the factory call site rather than passing a test context directly

## Proposed Approach: `ToolRuntime[RetailContext]`

Instead of the aircraft_analyst pattern (singleton class + lazy init + closure factory), refactor tools to use LangGraph's `ToolRuntime` dependency injection. Tools declare what they need; the framework injects it at invocation time. The same tool objects run in any environment — only the context differs.

| | aircraft_analyst (singleton + closure) | This proposal (ToolRuntime) |
|---|---|---|
| **Dependency binding** | `GraphAgent` singleton creates Neo4j driver lazily; tool closes over it | `RetailContext` dataclass injected per invocation |
| **Environment portability** | Must rebuild singleton per environment | Same tool objects everywhere; swap context |
| **Tool creation** | `create_tools(client)` factory returns closures | Flat `ALL_TOOLS` list at module level — no factory |
| **MLflow compatibility** | Singleton lazy-init avoids import-time connections | No connections at module level — tools are plain functions |
| **Type safety** | Closure is untyped | `RetailContext` is typed and inspectable |
| **Testing** | Mock the factory's arguments | Pass a test `RetailContext` directly |
| **Serving adapter** | `ResponsesAgent` with `predict`/`predict_stream` + `agent_helpers.py` | Thin `ChatAgent` shim (~5 lines of logic) |

## Architecture

```
backend/tools/
  context.py          - RetailContext dataclass (NEW)
  __init__.py          - Flat ALL_TOOLS list (REFACTORED from factory)
  product_search.py    - Refactored: ToolRuntime[RetailContext] parameter
  recommendations.py   - Refactored: ToolRuntime[RetailContext] parameter
  inventory.py         - Refactored: ToolRuntime[RetailContext] parameter
  cart.py              - Refactored: ToolRuntime[RetailContext] parameter
  memory_tools.py      - Refactored: ToolRuntime[RetailContext] parameter

backend/databricks_agent/
  agent.py             - create_react_agent with context_schema=RetailContext
  serving.py           - Thin ChatAgent shim for Model Serving
  config.py            - Deployment configuration (from aircraft_analyst pattern)
  deploy.py            - Log → Register → Deploy pipeline (from aircraft_analyst pattern)
  test_endpoint.py     - Endpoint verification script
```

The tool refactor is the bulk of the work. The deployment pipeline (`config.py`, `deploy.py`) ports directly from aircraft_analyst with retail-specific settings.

## Implementation Details

### 1. Define the Shared Context

```python
# backend/tools/context.py
from dataclasses import dataclass
from neo4j_agent_memory import MemoryClient

@dataclass
class RetailContext:
    """All external dependencies for retail agent tools.

    Injected by LangGraph at invocation time via ToolRuntime.
    Local FastAPI and Databricks Model Serving each construct
    their own RetailContext — tool code is identical in both.
    """
    client: MemoryClient
    session_id: str | None = None
```

### 2. Refactor Tools to Use `ToolRuntime`

Before (closure factory):

```python
# current: backend/tools/product_search.py
def create_product_search_tools(client: MemoryClient) -> list[BaseTool]:
    @tool(args_schema=SearchProductsInput)
    async def search_products(query: str, ...) -> str:
        embedding = await client._embedder.embed(query)       # closed over
        result = await client.graph.execute_read(cypher, params)  # closed over
        ...
    return [search_products, ...]
```

After (`ToolRuntime` injection):

```python
# proposed: backend/tools/product_search.py
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from backend.tools.context import RetailContext

@tool(args_schema=SearchProductsInput)
async def search_products(
    query: str,
    category: str | None = None,
    brand: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
    runtime: ToolRuntime[RetailContext],  # injected by LangGraph, hidden from LLM
) -> str:
    """Search the product catalog by query."""
    client = runtime.context.client
    embedding = await client._embedder.embed(query)
    result = await client.graph.execute_read(cypher, params)
    ...
```

The `runtime` parameter is reserved — LangGraph detects it by type hint and injects it automatically. It never appears in the tool schema sent to the LLM.

This refactor is applied to all 5 tool modules (product_search, recommendations, inventory, cart, memory_tools). The internal Cypher queries and business logic remain identical — only the way `client` is accessed changes.

### 3. Flat Tool List (No Factory)

```python
# proposed: backend/tools/__init__.py
from backend.tools.product_search import search_products, get_product_details, get_related_products
from backend.tools.recommendations import get_recommendations, get_bought_together, explain_product_connection
from backend.tools.inventory import check_inventory, find_alternatives
from backend.tools.cart import get_cart, add_to_cart, remove_from_cart, update_cart_item, clear_cart, apply_coupon
from backend.tools.memory_tools import search_memory

ALL_TOOLS = [
    search_products, get_product_details, get_related_products,
    get_recommendations, get_bought_together, explain_product_connection,
    check_inventory, find_alternatives,
    get_cart, add_to_cart, remove_from_cart, update_cart_item, clear_cart, apply_coupon,
    search_memory,
]
```

No factory function. No closures. Tools are plain module-level functions.

### 4. Build the Agent

```python
# backend/databricks_agent/agent.py
from databricks_langchain import ChatDatabricks
from langgraph.prebuilt import create_react_agent
from backend.tools import ALL_TOOLS
from backend.tools.context import RetailContext

SYSTEM_PROMPT = (
    "You are a retail product assistant with access to a Neo4j knowledge graph. "
    "Use your tools to search products, get recommendations, manage carts, "
    "check inventory, and recall user preferences from memory."
)

def create_retail_agent(llm=None):
    if llm is None:
        llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        context_schema=RetailContext,
        prompt=SYSTEM_PROMPT,
    )
```

No singleton. No lazy init. The agent graph is a pure function of its inputs. The `MemoryClient` connection is not created here — it lives in `RetailContext`, constructed by whoever invokes the agent.

### 5. Invocation — Same Agent, Different Context

```python
# Local FastAPI
from neo4j_agent_memory import MemoryClient
local_client = MemoryClient(...)
await local_client.connect()

result = agent.invoke(
    {"messages": [{"role": "user", "content": "find running shoes"}]},
    context=RetailContext(client=local_client, session_id=request.session_id),
)

# Databricks Model Serving — identical agent, different context
dbx_client = MemoryClient(uri=os.environ["NEO4J_URI"], password=os.environ["NEO4J_PASSWORD"])
await dbx_client.connect()

result = agent.invoke(
    {"messages": messages},
    context=RetailContext(client=dbx_client, session_id=session_id),
)
```

### 6. Thin `ChatAgent` Adapter for Databricks Serving

The `ChatAgent` wrapper is an I/O adapter for Databricks Model Serving, not the architecture. The agent logic lives in the LangGraph graph; this shim translates the serving protocol.

```python
# backend/databricks_agent/serving.py
import mlflow
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse
from backend.databricks_agent.agent import create_retail_agent
from backend.tools.context import RetailContext

class RetailKGAgent(ChatAgent):
    def __init__(self):
        self._agent = None
        self._context = None

    def _ensure_initialized(self):
        """Lazy init — credentials only available at serving time, not during log_model()."""
        if self._agent is None:
            from neo4j_agent_memory import MemoryClient
            client = MemoryClient(
                uri=os.environ["NEO4J_URI"],
                password=os.environ["NEO4J_PASSWORD"],
            )
            self._context = RetailContext(client=client)
            self._agent = create_retail_agent()

    def predict(self, messages, context=None, custom_inputs=None):
        """Sync entry point required by Databricks Model Serving.
        Bridges to async via asyncio.run() — see 'Async Tools in Model Serving' below.
        """
        return asyncio.run(self._async_predict(messages, context, custom_inputs))

    async def _async_predict(self, messages, context, custom_inputs):
        self._ensure_initialized()
        request = {"messages": [{"role": m.role, "content": m.content} for m in messages]}
        output = await self._agent.ainvoke(request, context=self._context)
        return ChatAgentResponse(messages=output["messages"])

AGENT = RetailKGAgent()
mlflow.models.set_model(AGENT)
```

**Design notes:**

- **Lazy init** is still needed in the serving adapter (same as aircraft_analyst) because MLflow imports the module during `log_model()` when no secrets are available. But this is confined to the thin adapter — the tools and agent themselves have no lazy-init machinery.
- **`asyncio.run()` bridge** — `ChatAgent.predict()` is sync, but all 15 tools and the `neo4j-agent-memory` client are async-only. The bridge delegates to `ainvoke()` which runs async tools natively. See the "Async Tools in Model Serving" section below for rationale.

### 7. Configuration (`config.py`)

Ported from aircraft_analyst with retail-specific defaults. Dataclass with environment variable overrides using the pattern `RETAIL_AGENT_<SETTING>`.

```python
@dataclass
class DeployConfig:
    # Unity Catalog
    catalog: str = "retail"
    schema: str = "default"
    model_name: str = "neo4j_kg_agent"

    # Secrets
    secret_scope: str = "retail-agent-secrets"

    # LLM
    llm_endpoint: str = "databricks-meta-llama-3-3-70b-instruct"

    # Deployment
    scale_to_zero: bool = True
    max_wait_seconds: int = 600
```

**Secrets mapping** (same `{{secrets/scope/key}}` pattern as aircraft_analyst):

```
NEO4J_URI       → {{secrets/retail-agent-secrets/neo4j-uri}}
NEO4J_PASSWORD  → {{secrets/retail-agent-secrets/neo4j-password}}
OPENAI_API_KEY  → {{secrets/retail-agent-secrets/openai-api-key}}  (only if using OpenAI LLM)
```

### 8. Deployment (`deploy.py`)

Four-step pipeline, ported from aircraft_analyst:

1. **Log model** with MLflow Models from Code — points at `serving.py`, includes tool modules as `code_paths`
2. **Register** in Unity Catalog as `retail.default.neo4j_kg_agent`
3. **Deploy** via `agents.deploy()` with secret-backed environment variables
4. **Wait** for endpoint to reach `READY` state

```python
mlflow.langchain.log_model(
    lc_model="./serving.py",  # Models-from-Code
    name="neo4j_kg_agent",
    pip_requirements=[
        "mlflow>=3.1",
        "langgraph>=1.0.0",
        "langchain-core>=0.3.0",
        "databricks-langchain>=0.15.0",
        "neo4j>=5.17.0,<6.0.0",
        "neo4j-agent-memory",
    ],
)
```

## Secrets Setup

```bash
databricks secrets create-scope retail-agent-secrets
databricks secrets put-secret retail-agent-secrets neo4j-uri --string-value "neo4j+s://xxx.databases.neo4j.io:7687"
databricks secrets put-secret retail-agent-secrets neo4j-password --string-value "..."
databricks secrets put-secret retail-agent-secrets openai-api-key --string-value "sk-..."  # if using OpenAI
```

## What Changes vs. What's New vs. What's Ported

| Component | Action | Source |
|-----------|--------|--------|
| `backend/tools/context.py` | **New** | `RetailContext` dataclass |
| `backend/tools/__init__.py` | **Refactor** | Replace `create_tools()` factory with flat `ALL_TOOLS` |
| `backend/tools/*.py` (5 modules) | **Refactor** | Replace closure over `client` with `ToolRuntime[RetailContext]` parameter |
| `backend/databricks_agent/agent.py` | **New** | `create_react_agent` with `context_schema=RetailContext` |
| `backend/databricks_agent/serving.py` | **New** (thin) | `ChatAgent` shim with lazy init for serving |
| `backend/databricks_agent/config.py` | **Port** from aircraft_analyst | Adapt UC names, secrets, endpoint settings |
| `backend/databricks_agent/deploy.py` | **Port** from aircraft_analyst | Same 4-step pipeline, retail-specific config |
| `backend/databricks_agent/test_endpoint.py` | **Port** from aircraft_analyst | Adapt test queries for retail domain |

## Impact on Existing FastAPI Backend

The tool refactor changes the signature of every tool function (adding `runtime: ToolRuntime[RetailContext]`), but the internal logic is unchanged. The FastAPI backend currently calls `create_tools(client)` — after the refactor, it would instead:

1. Construct a `RetailContext(client=memory_client, session_id=...)`
2. Import `ALL_TOOLS` and pass them to the agent
3. Invoke with `context=retail_context`

This is a breaking change to the tools API surface, but the FastAPI chat endpoints are currently placeholders (Phase 7 not yet wired), so the migration cost is minimal.

## Async Tools in Model Serving (Resolved)

All 15 tools are `async def` and the `neo4j-agent-memory` library (`/Users/ryanknight/projects/neo4j-labs/agent-memory`) is **async-only throughout** — there is no sync escape hatch:

| Component | API | Sync alternative? |
|---|---|---|
| `MemoryClient.connect()` | `async` | No |
| `client.graph.execute_read/write()` | `async` (uses `AsyncDriver` / `AsyncGraphDatabase`) | No |
| `client._embedder.embed()` | `async` | No |
| `client.long_term.search_preferences()` | `async` | No |

Converting tools to sync is not viable without rewriting the memory library. The tools stay async. This is the right call for three reasons:

1. **LangGraph handles it natively** — `await agent.ainvoke()` runs async tools without wrapping. The `ToolNode` calls `ainvoke()` on each tool in an async context.
2. **Parallel tool execution** — when the LLM requests multiple tools in one turn, LangGraph can run async tools concurrently. Sync tools would block the event loop and execute sequentially.
3. **The Databricks sync gap is a one-line bridge** — MLflow's `ChatAgent.predict()` is sync, but `asyncio.run()` in the adapter bridges cleanly to `ainvoke()`. This is the pattern shown in the serving adapter above. LangChain docs confirm: sync→async promotion is automatic (via `run_in_executor`), but async→sync requires manual bridging — and `asyncio.run()` is the recommended approach.

**Key asymmetry to be aware of:** LangChain's `@tool` on `async def` sets only the `coroutine` on `StructuredTool`. If sync `invoke()` is called on an async-only tool, it raises `NotImplementedError`. Always use `ainvoke()` / `agent.ainvoke()` when calling the agent, and bridge at the serving boundary only.

## Open Questions

1. **MemoryClient packaging** — `neo4j-agent-memory` is currently installed as a local editable package (`uv pip install -e`). For Databricks serving, it needs to be either published to PyPI or included as a wheel in the MLflow artifact. Which approach do we prefer?
2. **Session/cart state** — Cart tools use Neo4j MERGE with a `session_id`. With `ToolRuntime`, this flows naturally via `RetailContext.session_id`. But how does the supervisor pass session identity down to the sub-agent? LangGraph's `config` dict or `context` parameter are both options.
3. **Vector index** — `search_products` calls `db.index.vector.queryNodes()`. The Neo4j Aura instance must have the vector index pre-created. Is this already set up, or does it need to be part of the deployment runbook?
4. **`ToolRuntime` bugs in `ToolNode`** — There are active LangGraph issues ([#6318](https://github.com/langchain-ai/langgraph/issues/6318), [#6431](https://github.com/langchain-ai/langgraph/issues/6431)) where `ToolRuntime` injection fails in `ToolNode` with Pydantic validation errors. Before committing to `ToolRuntime[RetailContext]`, we must verify against the pinned `langgraph` version. Fallback: use `InjectedToolArg` (from `langchain_core.tools`) with `get_runtime()` inside the tool body, or write a custom `ToolNode` wrapper that injects the context manually.

## Import Path Correction

> **Note (Feb 2026):** The `ToolRuntime` class lives in `langgraph.prebuilt`, **not** `langchain_core.tools`. The correct imports are:
>
> ```python
> from langchain_core.tools import tool          # @tool decorator
> from langgraph.prebuilt import ToolRuntime      # runtime injection type
> ```
>
> The `InjectedToolArg` fallback is in `langchain_core.tools`:
>
> ```python
> from langchain_core.tools import InjectedToolArg
> ```
>
> Verified with langgraph 1.0.8 / langchain-core 1.2.13.
>
> Related issues:
> - [ToolRuntime not supported in ToolNode #6318](https://github.com/langchain-ai/langgraph/issues/6318)
> - [runtime not passed with Pydantic BaseModel args_schema #33646](https://github.com/langchain-ai/langchain/issues/33646)

## References

- **aircraft_analyst reference project**: `/Users/ryanknight/projects/aircraft_analyst/` — see `DATABRICKS_AGENT.md` for the deployment pipeline pattern (MLflow Models-from-Code, `agents.deploy()`, secrets mapping, endpoint testing)
- [LangGraph create_react_agent reference](https://langchain-ai.github.io/langgraph/reference/prebuilt/#create_react_agent)
- [LangChain Runtime docs](https://docs.langchain.com/oss/python/langchain/runtime) — ToolRuntime usage and context injection
- [LangChain ToolRuntime / runtime injection](https://python.langchain.com/docs/how_to/tool_configure/)
- [MLflow Models-from-Code for LangGraph](https://mlflow.org/blog/langgraph-model-from-code)
- [Mosaic AI Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [Deploy an agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/deploy-agent)
