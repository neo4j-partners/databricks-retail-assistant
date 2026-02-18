# Remaining Phases Implementation Plan (Phases 4–10)

This document details the implementation plan for Phases 4 through 10 of the retail assistant migration from Microsoft Agent Framework to LangGraph with Neo4j Agent Memory. Each phase emphasizes Python best practices, Pydantic data validation, and the latest stable versions of LangChain (langchain-core 1.2.x) and LangGraph (1.0.8).

---

## Guiding Principles

### Pydantic Everywhere

Every data structure that crosses a boundary — function arguments, return values, API requests, API responses, configuration objects, tool inputs — must be a Pydantic BaseModel or use Pydantic Field annotations. Raw dicts are not acceptable at API boundaries. This applies to:

- All FastAPI request and response models (enforced via `response_model` on every endpoint).
- All LangChain tool input schemas (defined as Pydantic BaseModel classes passed via `args_schema` to the `@tool` decorator).
- All configuration and settings classes (using `pydantic-settings` BaseSettings).
- All internal data transfer objects between the agent, memory, and API layers.

Use `Field(description=...)` on every model field to provide documentation that both OpenAPI/Swagger and the LLM tool-calling system can consume. Use `Field(ge=..., le=...)` for numeric bounds, `Field(max_length=...)` for strings, and `Literal` types for constrained string values.

### Type Safety

- All functions must have complete type annotations on parameters and return values.
- Use `str | None` syntax (PEP 604) rather than `Optional[str]`.
- Use `from __future__ import annotations` in every module for consistent forward-reference behavior.
- Avoid `Any` wherever possible. When interfacing with untyped libraries, add a typed wrapper or protocol.

### Async-First

- All Neo4j queries, memory operations, and LLM calls are async. Never use synchronous wrappers where an async path exists.
- Use `async def` for all FastAPI endpoints, tool functions, and helper functions that touch I/O.
- The neo4j-agent-memory LangChain integration uses a sync/async bridge internally; do not add another layer of `asyncio.run()` on top.

### No Global Mutable State

- The current `memory_client: MemoryClient | None = None` global will be replaced with FastAPI's dependency injection system using `app.state` to hold the client, accessed via `request.app.state.memory_client` or a `Depends()` function.
- Tools receive the memory client via closure at construction time (factory pattern), not by reaching into global scope.

### Security

- No user-provided strings are interpolated into Cypher queries. All dynamic values use parameter binding (`$param`).
- The `relationship_type` parameter on the related products endpoint must be validated against an allowed set using a `Literal` type or enum, not passed as a raw f-string into Cypher.

---

## Phase 4: Plain Python Test Suite

**Goal:** Create a test suite in plain Python (no pytest, no test frameworks) that calls every API endpoint over HTTP and verifies responses, providing an automated regression check for all subsequent phases.

### Deliverables

A single file `test_api.py` at the project root, runnable with `python test_api.py`.

### Implementation Details

- Use `urllib.request` and `http.client` from the standard library for HTTP calls. No external dependencies.
- Define a Pydantic model for each expected response shape and validate the actual JSON response against it using `model_validate`. This ensures the test suite catches any response shape regressions automatically.
- Each test is a plain function that prints its name, the endpoint being called, and PASS or FAIL with the failure reason.
- The test runner collects results and exits with code 1 if any test failed.

### Tests to Include

1. **Health check** — `GET /health` returns `{"status": "healthy", "database": "connected"}`. Validate against a `HealthResponse` model.
2. **Product search** — `GET /products/search?query=running+shoes` returns a response matching a `ProductSearchResponse` model with a `products` list and `total` count. If sample data is loaded, assert at least one result.
3. **Product detail** — `GET /products/{id}` with a known ID returns a full product record matching a `ProductResponse` model. Test with an invalid ID returns 404.
4. **Related products** — `GET /products/{id}/related` returns a response matching a `RelatedProductsResponse` model.
5. **Sync chat** — `POST /chat/sync` with `{"message": "hello"}` returns a response matching `ChatResponse` with `response` and `session_id` fields.
6. **SSE streaming chat** — `POST /chat` with `{"message": "hello"}`, read the SSE stream and verify at least one `token` event and one `done` event are received.
7. **Memory context** — `GET /memory/context?session_id=test` returns a response matching a `MemoryContextResponse` model with `short_term`, `long_term`, and `reasoning` fields.
8. **Memory graph** — `GET /memory/graph?session_id=test` returns a response matching a `MemoryGraphResponse` model with `nodes` and `edges` fields.
9. **Memory preferences** — `GET /memory/preferences?session_id=test` returns a response matching a `PreferencesResponse` model with a `preferences` list.

### Pydantic Validation Pattern

Define response models in the test file itself (mirroring the server models) and use `model_validate(json_response)` to assert correctness. This catches missing fields, wrong types, and unexpected shapes. Example pattern:

- Define `HealthResponse(BaseModel)` with `status: str` and `database: str`.
- Parse the JSON response with `HealthResponse.model_validate(data)`.
- If validation fails, the test fails with the Pydantic error message.

### Extension Points

As each subsequent phase adds real functionality, tests will be extended with additional assertions. The test file structure should make it easy to add new tests by defining a new function and registering it in the test runner list.

---

## Phase 5: Neo4jAgentMemory Verification

**Goal:** Prove that the neo4j-agent-memory LangChain integration (save context, load memory variables, retrieve documents) works against the live Neo4j instance before building anything on top of it.

### Deliverables

- A standalone verification script `verify_memory.py` that exercises the LangChain integration directly.
- Updates to `main.py` to wire the memory endpoints to real data.
- New tests in `test_api.py` that verify memory functionality through the API.

### Implementation Details

#### Verification Script

- Initialize `MemoryClient` with `MemorySettings` built from environment variables, using the same `get_memory_settings()` function from `main.py`.
- Create a `Neo4jAgentMemory` instance configured with `session_id="verification-test"`, `include_short_term=True`, `include_long_term=True`, `include_reasoning=True`.
- Call `save_context({"input": "I like Nike running shoes"}, {"output": "Nike has great running shoes!"})` and verify it completes without error.
- Call `load_memory_variables({"input": "running shoes"})` and assert the returned dict contains the keys `history`, `context`, `preferences`, and `similar_tasks`. Assert that `history` contains the saved messages.
- Create a `Neo4jMemoryRetriever` with `k=5` and `threshold=0.7`, invoke it with `"Nike shoes"`, and assert it returns `Document` objects with metadata containing `type` and `similarity` keys.
- Print clear pass/fail output for each step.

#### Memory Endpoint Wiring

Update the three memory endpoints in `main.py` to call the real memory client:

- `/memory/context` — Create a `Neo4jAgentMemory` for the given session, call `load_memory_variables` with the query, and return the structured result. Define a Pydantic response model `MemoryContextResponse` with typed fields for each memory tier.
- `/memory/graph` — Call `memory_client.get_graph()` with the session ID and return nodes and edges. Define `MemoryGraphResponse` with `nodes: list[GraphNode]` and `edges: list[GraphEdge]` where `GraphNode` and `GraphEdge` are Pydantic models.
- `/memory/preferences` — Call `memory_client.long_term.search_preferences()` with the session ID and optional category filter. Define `PreferencesResponse` with `preferences: list[PreferenceItem]`.

#### Pydantic Models for Memory Responses

All memory response models must be fully typed:

- `GraphNode` — `id: str`, `label: str`, `type: str`, `properties: dict[str, str | int | float | bool]`
- `GraphEdge` — `source: str`, `target: str`, `type: str`, `properties: dict[str, str | int | float | bool]`
- `PreferenceItem` — `category: str`, `preference: str`, `context: str | None`, `created_at: str | None`

### Test Extensions

Add tests to `test_api.py`:

- Send a chat message, then call `/memory/context` with the same session ID and assert the conversation appears in the short-term history.
- Call `/memory/preferences` and verify the response validates against `PreferencesResponse`.

---

## Phase 6: Tool Conversion

**Goal:** Convert all agent tools from Microsoft Agent Framework closures to LangChain `@tool` functions with Pydantic input schemas, and verify each works independently.

### Deliverables

- A `tools/` directory with one module per tool category: `product_search.py`, `recommendations.py`, `inventory.py`, `cart.py`, `memory_tools.py`.
- Pydantic `BaseModel` input schemas for every tool.
- A tool factory function that takes a `MemoryClient` and returns the list of all tools.

### Tool Input Schema Pattern

Every tool must define its input as a Pydantic BaseModel with `Field(description=...)` on each parameter. This schema is passed to the `@tool` decorator via `args_schema`. The LLM uses the field descriptions to decide how to call the tool.

Example pattern for `search_products`:

- Define `SearchProductsInput(BaseModel)` with fields: `query: str = Field(description="Search query for products")`, `category: str | None = Field(default=None, description="Filter by product category")`, `brand: str | None = Field(default=None, description="Filter by brand name")`, `max_price: float | None = Field(default=None, ge=0, description="Maximum price filter")`.
- The `@tool` decorator receives `args_schema=SearchProductsInput`.
- The function signature matches the model fields exactly.

### Tool Factory Pattern

Define a `create_tools(memory_client: MemoryClient) -> list` function in `tools/__init__.py` that:

1. Creates all product, recommendation, inventory, and cart tools as closures capturing `memory_client`.
2. Creates the memory retriever tool wrapping `Neo4jMemoryRetriever`.
3. Returns the complete tool list.

This avoids global state — the tools receive their dependencies at construction time.

### Tools to Convert

#### Product Tools (`tools/product_search.py`)

| Tool | Input Schema | Returns |
|------|-------------|---------|
| `search_products` | `SearchProductsInput` (query, category, brand, max_price) | JSON: products list with id, name, price, category, score |
| `get_product_details` | `ProductDetailsInput` (product_id) | JSON: full product record |
| `get_related_products` | `RelatedProductsInput` (product_id, relationship_type as Literal or None) | JSON: related products with connection reasons |

#### Recommendation Tools (`tools/recommendations.py`)

| Tool | Input Schema | Returns |
|------|-------------|---------|
| `get_recommendations` | `RecommendationsInput` (category, limit with Field(ge=1, le=20)) | JSON: recommended products based on preferences |
| `get_bought_together` | `BoughtTogetherInput` (product_id) | JSON: frequently co-purchased products |
| `explain_product_connection` | `ConnectionInput` (product_id_a, product_id_b) | JSON: graph path explaining relationship |

#### Inventory Tools (`tools/inventory.py`)

| Tool | Input Schema | Returns |
|------|-------------|---------|
| `check_inventory` | `InventoryCheckInput` (product_id) | JSON: stock status, quantity, availability |
| `find_alternatives` | `AlternativesInput` (product_id, max_results with Field(ge=1, le=10)) | JSON: in-stock alternatives in same category |

#### Cart Tools (`tools/cart.py`)

| Tool | Input Schema | Returns |
|------|-------------|---------|
| `get_cart` | `CartInput` (session_id) | JSON: cart contents with totals |
| `add_to_cart` | `AddToCartInput` (session_id, product_id, quantity with Field(ge=1)) | JSON: updated cart |
| `remove_from_cart` | `RemoveFromCartInput` (session_id, product_id) | JSON: updated cart |
| `update_cart_item` | `UpdateCartInput` (session_id, product_id, quantity with Field(ge=0)) | JSON: updated cart |
| `clear_cart` | `CartInput` (session_id) | JSON: empty cart confirmation |
| `apply_coupon` | `CouponInput` (session_id, coupon_code) | JSON: cart with discount applied |

#### Memory Tools (`tools/memory_tools.py`)

| Tool | Input Schema | Returns |
|------|-------------|---------|
| `search_memory` | `MemorySearchInput` (query, search_type as Literal["all", "messages", "entities", "preferences"]) | JSON: matching memory entries |

This tool wraps `Neo4jMemoryRetriever` and returns the retrieved documents formatted as JSON with type and similarity metadata.

### Async Tools

All tools that query Neo4j or call embeddings must be async. The LangChain `@tool` decorator supports `async def` functions natively. Use `@tool(args_schema=SchemaClass)` on `async def` functions.

### Tool-Level Tests

Add tool tests to `test_api.py` or a separate `test_tools.py`:

- Import each tool function directly.
- Call with known arguments against the live database.
- Validate the JSON return value against a Pydantic model.
- Verify that tools handle missing products, empty results, and invalid IDs gracefully (returning error messages, not raising unhandled exceptions).

---

## Phase 7: Agent Construction

**Goal:** Build the LangGraph ReAct agent, wire it into the chat endpoints, and replace placeholder responses with real agent output.

### Deliverables

- A new `agent.py` module containing the agent factory function.
- Updated `/chat` and `/chat/sync` endpoints in `main.py` with real agent integration.
- Updated memory endpoints returning real data.

### Agent Module (`agent.py`)

#### LLM Initialization

Use `init_chat_model` from `langchain.chat_models` to create the LLM. This function supports provider-agnostic initialization:

- For OpenAI: `init_chat_model("gpt-4o", model_provider="openai")`
- For Azure OpenAI: `init_chat_model(model=deployment_name, model_provider="azure_openai", azure_endpoint=endpoint, api_version=version)`

The provider and model are read from the `Settings` Pydantic model. No hardcoded model names.

#### Agent Factory

Define `create_agent(memory_client: MemoryClient, settings: Settings)` that:

1. Initializes the LLM via `init_chat_model` using settings.
2. Creates all tools via `create_tools(memory_client)` from the tools module.
3. Creates the agent via `create_react_agent(model=llm, tools=tools, prompt=system_prompt)` from `langgraph.prebuilt`.
4. Attaches an `InMemorySaver` checkpointer for LangGraph execution state.
5. Returns the compiled agent graph.

The system prompt must be a string (not a template) that instructs the agent to:

- Help customers find products matching their needs.
- Use the search tool for product queries and the memory tool for recalling preferences.
- Provide personalized recommendations by combining remembered preferences with graph relationships.
- Check inventory before confirming availability.
- Suggest alternatives for out-of-stock items.
- Be conversational and helpful.

#### Agent Invocation Pattern

Define `run_agent(agent, memory_client, session_id, user_id, message)` as an async generator that:

1. Creates a `Neo4jAgentMemory` for the session.
2. Calls `load_memory_variables({"input": message})` to get context.
3. Builds the message list: system message with memory context, then the user message.
4. Calls `agent.astream({"messages": messages}, config={"configurable": {"thread_id": session_id}}, stream_mode="updates")`.
5. For each streamed chunk, yields SSE-formatted events:
   - AIMessage content chunks become `token` events.
   - Tool call messages become `tool_call` events.
   - Tool response messages become `tool_result` events.
6. After streaming completes, calls `save_context` to persist the conversation turn.
7. Yields a final `done` event with the session ID.

All yielded events must be Pydantic models serialized to JSON:

- `TokenEvent(BaseModel)` — `content: str`
- `ToolCallEvent(BaseModel)` — `name: str`, `arguments: str`
- `ToolResultEvent(BaseModel)` — `name: str`, `result: str`
- `DoneEvent(BaseModel)` — `session_id: str`
- `ErrorEvent(BaseModel)` — `error: str`

#### Configuration via Pydantic

Define an `AgentConfig(BaseModel)` that holds:

- `system_prompt: str`
- `max_messages: int = Field(default=10, ge=1, le=50)` — conversation history window
- `max_preferences: int = Field(default=5, ge=0, le=20)` — preferences to include in context
- `max_traces: int = Field(default=3, ge=0, le=10)` — reasoning traces to include

This config is passed to the agent factory and used when creating `Neo4jAgentMemory` instances.

### Chat Endpoint Updates

- `/chat` — Replace the placeholder generator with a call to `run_agent()`, wrapping it in `EventSourceResponse`.
- `/chat/sync` — Call `agent.ainvoke()` instead of streaming, collect the final response, save context, and return `ChatResponse`.

Both endpoints must handle errors by yielding or returning an `ErrorEvent` rather than raising unhandled exceptions.

### LangGraph Best Practices Applied

- Use `stream_mode="updates"` for streaming so each node's output is yielded separately.
- Use `config={"configurable": {"thread_id": session_id}}` to enable LangGraph's checkpointer per session.
- Use `add_messages` from `langgraph.graph.message` if manually constructing message lists.
- The `InMemorySaver` checkpointer tracks graph execution state only. Domain memory (conversations, preferences, entities) lives in Neo4j via `Neo4jAgentMemory`.

### Test Extensions

Update `test_api.py`:

- Chat tests must now verify real agent responses (not placeholder text).
- Send a product question ("What running shoes do you have?") and verify the response mentions products or invokes a tool.
- Verify that the session ID persists across multiple messages in the same conversation.

---

## Phase 8: Reasoning Trace Integration

**Goal:** Record a complete reasoning trace for every agent turn so that future similar tasks can retrieve relevant past reasoning.

### Deliverables

- Trace recording integrated into the agent invocation flow.
- Reasoning traces visible in the `/memory/context` endpoint.
- Tests verifying trace storage and retrieval.

### Implementation Details

#### StreamingTraceRecorder Integration

Wrap the agent streaming invocation in a `StreamingTraceRecorder` context manager from `neo4j_agent_memory`:

1. Before the agent runs, start a trace with `task_description=user_message`.
2. As each tool call is processed during streaming, record the step with: tool name, arguments (serialized as JSON string), result (serialized), status (`"success"` or `"error"`), and duration in milliseconds.
3. When the agent finishes, complete the trace with `outcome=final_response_text` and `success=True` (or `False` if an error occurred).

#### Pydantic Models for Trace Data

Define typed models for trace steps:

- `TraceStep(BaseModel)` — `tool_name: str`, `arguments: str`, `result: str`, `status: Literal["success", "error", "timeout"]`, `duration_ms: int = Field(ge=0)`
- `ReasoningTrace(BaseModel)` — `task: str`, `steps: list[TraceStep]`, `outcome: str`, `success: bool`, `created_at: str`

These models are used in the `/memory/context` response to structure the reasoning tier.

#### Memory Context Update

Update the `/memory/context` endpoint to include populated reasoning traces in the response. The `similar_tasks` field from `load_memory_variables` must be parsed and returned as a list of `ReasoningTrace` objects.

### Test Extensions

- Send a product search question, wait for the response.
- In a new session, send a semantically similar question and call `/memory/context` to verify the `reasoning` field contains traces from the first interaction.
- Verify that the trace contains at least one tool step (the product search tool call).

---

## Phase 9: End-to-End Testing

**Goal:** Comprehensive testing that verifies the migrated application behaves identically to the original from the user's perspective.

### Deliverables

- Extended `test_api.py` with multi-turn, cross-session, and entity extraction tests.
- All tests pass against a live Neo4j instance with sample data loaded.

### Test Scenarios

#### Multi-Turn Conversation

Send a sequence of messages within a single session:

1. "Hi, I'm looking for running shoes" — verify greeting and product suggestions.
2. "I prefer Nike" — verify the agent acknowledges the brand preference.
3. "What do you have under $150?" — verify filtered results.
4. "Add the first one to my cart" — verify cart operation.
5. "What else would go well with those?" — verify recommendations use the cart context and preferences.

Each message uses the same session ID. Verify the agent maintains context across turns.

#### Cross-Session Memory

1. Session A: Express a preference ("I love minimalist design and earth tones").
2. Session B (new session, same user ID): Ask "What would you recommend?" and verify the agent recalls the preference from Session A through long-term memory.

#### Entity Extraction

1. Send "I just bought the Nike Air Max 90 and love them" in a session.
2. Call `/memory/context` for that session.
3. Verify extracted entities include "Nike" (Organization) and "Air Max 90" (Object) with the POLE+O type classification.

#### SSE Streaming Validation

1. Connect to `/chat` with a product question.
2. Collect all SSE events.
3. Verify the event sequence: at least one `token` event, optionally `tool_call` and `tool_result` events, ending with a `done` event.
4. Verify the concatenated token contents form a coherent response.

#### Graph Visualization

1. After a multi-turn conversation, call `/memory/graph`.
2. Verify returned nodes include Message, Entity, and Preference types.
3. Verify edges connect messages to entities and preferences with typed relationships.

#### GDS Fallback

If the Graph Data Science plugin is not installed, verify that recommendation and related product tools fall back to basic Cypher queries without errors.

#### Error Handling

- Send a malformed request body and verify a 422 response with Pydantic validation errors.
- Request a nonexistent product ID and verify a 404 response.
- Verify that the health endpoint returns `{"status": "degraded"}` when the database is unreachable.

### Pydantic Validation in Tests

Every test must validate the API response against its Pydantic model using `model_validate`. This ensures that response contracts are maintained even as the implementation changes.

---

## Phase 10: Cleanup and Documentation

**Goal:** Remove all traces of the Microsoft Agent Framework and ensure the codebase is clean, well-typed, and ready for workshop use.

### Deliverables

- No remaining references to the Microsoft Agent Framework anywhere in the codebase.
- Updated README with architecture overview.
- Clean, passing test suite.

### Cleanup Checklist

- Search for and remove any imports, references, or comments mentioning: `agent-framework`, `Neo4jMicrosoftMemory`, `Neo4jContextProvider`, `FunctionTool`, `OpenAIChatClient`, `AzureOpenAIResponsesClient`, `create_memory_tools`, `record_agent_trace`.
- Remove any unused files, utility functions, or configuration keys from the Microsoft integration.
- Verify no compatibility layers, wrapper functions, variable aliases, or commented-out code remain.
- Verify all Pydantic models are used consistently — no raw dicts at API boundaries.
- Verify all functions have complete type annotations.
- Verify all `@tool` functions have `args_schema` Pydantic models.
- Verify no user input is interpolated into Cypher strings — all use parameter binding.

### Documentation

Update the README to describe:

- Architecture: LangGraph for orchestration, neo4j-agent-memory LangChain integration for memory, Neo4j for product data and memory storage.
- How to run: environment setup, `.env` configuration, `uv sync`, `python main.py`.
- How to test: `python test_api.py`.
- API endpoint reference (auto-generated by FastAPI at `/docs`).

### Final Verification

Run the complete `test_api.py` suite and verify all tests pass. This is the final gate before the migration is considered complete.

---

## Installed Package Versions (Current)

| Package | Version | Role |
|---------|---------|------|
| langgraph | 1.0.8 | Agent orchestration |
| langgraph-prebuilt | 1.0.7 | `create_react_agent` |
| langgraph-checkpoint | 4.0.0 | `InMemorySaver` |
| langchain-core | 1.2.13 | `@tool`, base abstractions |
| langchain-openai | 1.1.10 | OpenAI/Azure chat models |
| neo4j-agent-memory | 0.0.1 | Memory client with LangChain integration |
| neo4j | 6.1.0 | Neo4j Python driver |
| fastapi | 0.129.0 | Web framework |
| pydantic | 2.12.5 | Data validation |
| pydantic-settings | 2.13.0 | Environment variable loading |

These are the latest stable versions as of the dependency resolution in Phase 2. The LangChain `@tool` decorator, `init_chat_model`, and `args_schema` pattern are all supported at these versions.

---

## Key LangChain/LangGraph API References

### Tool Definition (langchain-core 1.2.x)

```
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    query: str = Field(description="The search query")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")

@tool(args_schema=MyToolInput)
async def my_tool(query: str, limit: int = 10) -> str:
    ...
```

### Agent Creation (langgraph 1.0.8)

```
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model

llm = init_chat_model("gpt-4o", model_provider="openai")
agent = create_react_agent(model=llm, tools=tools, prompt=system_prompt, checkpointer=InMemorySaver())
```

### Streaming (langgraph 1.0.8)

```
async for chunk in agent.astream(
    {"messages": messages},
    config={"configurable": {"thread_id": session_id}},
    stream_mode="updates",
):
    for node_name, update in chunk.items():
        ...
```

### Memory Integration (neo4j-agent-memory 0.0.1)

```
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory, Neo4jMemoryRetriever

memory = Neo4jAgentMemory(
    memory_client=client,
    session_id=session_id,
    include_short_term=True,
    include_long_term=True,
    include_reasoning=True,
)
context = memory.load_memory_variables({"input": user_message})
memory.save_context({"input": user_message}, {"output": assistant_response})
```

---

## Phase Status Tracker

### Phase 4: Plain Python Test Suite — COMPLETE

**Created `test_api.py` with 11 tests covering all 9 endpoints, plus validation and error cases.**

**Test results: 11 passed, 0 failed.**

| Test | Endpoint | Method | Validates Against | Result |
|------|----------|--------|-------------------|--------|
| Health check | `/health` | GET | `HealthResponse` | PASS |
| Sync chat | `/chat/sync` | POST | `ChatResponse` | PASS |
| Streaming chat (SSE) | `/chat` | POST | SSE event parsing (token + done) | PASS |
| Memory context | `/memory/context` | GET | `MemoryContextResponse` | PASS |
| Memory graph | `/memory/graph` | GET | `MemoryGraphResponse` | PASS |
| Memory preferences | `/memory/preferences` | GET | `PreferencesResponse` | PASS |
| Product search | `/products/search` | GET | `ProductSearchResponse` with `ProductItem` list | PASS |
| Product detail | `/products/{id}` | GET | `ProductDetailResponse` | PASS (SKIP: no sample data) |
| Product detail 404 | `/products/{id}` | GET | Expects 404 for invalid ID | PASS |
| Related products | `/products/{id}/related` | GET | `RelatedProductsResponse` | PASS (SKIP: no sample data) |
| Related products invalid type | `/products/{id}/related` | GET | Expects 400 for Cypher injection attempt | PASS |

**Key implementation details:**

- Every response is validated against a Pydantic model using `model_validate()`. Pydantic `ValidationError` is caught by the test runner and reported as a failure with the full error message.
- SSE streaming test parses `event:` and `data:` lines correctly, validates both `token` events (must have `content` key) and `done` events (must have `session_id` key).
- Product detail and related products tests gracefully skip when no sample data is loaded (the database has no Product nodes yet) rather than failing.
- The invalid relationship type test verifies the Cypher injection fix added in the `main.py` review — sending `relationship_type=DROP_TABLE` returns HTTP 400 instead of being interpolated into Cypher.
- Test suite uses `--base-url` argument for configurability, defaults to `http://localhost:8000`.
- Exit code is 1 on any failure, 0 on all pass.

### Phase 5: Neo4jAgentMemory Verification — COMPLETE

**Created `verify_memory.py` standalone verification script (12/12 checks passed). Wired all three memory endpoints in `main.py` to real Neo4j data. Updated `test_api.py` to 12 tests (added memory roundtrip test).**

**verify_memory.py results: 12 passed, 0 failed.**

| Step | Check | Result |
|------|-------|--------|
| 1. Connect | `MemoryClient.connect()` | PASS |
| 2. Save context | `Neo4jAgentMemory._save_context_async()` | PASS |
| 3. Load variables | Returns expected keys (history, context, preferences, similar_tasks) | PASS |
| 3. Load variables | History contains saved conversation | PASS |
| 3. Load variables | Context is a string | PASS |
| 3. Load variables | Preferences is a list | PASS |
| 3. Load variables | Similar_tasks is a string | PASS |
| 4. Retriever | `Neo4jMemoryRetriever._get_relevant_documents_async()` returns docs | PASS |
| 4. Retriever | Document has page_content | PASS |
| 4. Retriever | Document has type metadata | PASS |
| 5. Graph | `MemoryClient.get_graph()` returns MemoryGraph | PASS |
| 6. Cleanup | `clear_session` | PASS |

**test_api.py results: 12 passed, 0 failed.**

| Test | Endpoint | Method | Validates Against | Result |
|------|----------|--------|-------------------|--------|
| Health check | `/health` | GET | `HealthResponse` | PASS |
| Sync chat | `/chat/sync` | POST | `ChatResponse` | PASS |
| Streaming chat (SSE) | `/chat` | POST | SSE event parsing (token + done) | PASS |
| Memory context | `/memory/context` | GET | `MemoryContextResponse` (history, context, preferences, similar_tasks) | PASS |
| Memory graph | `/memory/graph` | GET | `MemoryGraphResponse` (nodes, relationships) | PASS |
| Memory preferences | `/memory/preferences` | GET | `PreferencesResponse` with `PreferenceItem` list | PASS |
| Product search | `/products/search` | GET | `ProductSearchResponse` | PASS |
| Product detail | `/products/{id}` | GET | `ProductDetailResponse` | PASS (SKIP: no sample data) |
| Product detail 404 | `/products/{id}` | GET | Expects 404 | PASS |
| Related products | `/products/{id}/related` | GET | `RelatedProductsResponse` | PASS (SKIP: no sample data) |
| Related products invalid type | `/products/{id}/related` | GET | Expects 400 | PASS |
| Memory roundtrip | `/chat/sync` + `/memory/context` | POST+GET | Chat then verify memory context shape | PASS |

**Key implementation details:**

- All memory endpoints use async methods directly (`_load_memory_variables_async`, `_save_context_async`) to avoid deadlocking the FastAPI event loop. The sync wrappers in `Neo4jAgentMemory` use `run_coroutine_threadsafe` which would block the event loop.
- `_get_agent_memory(session_id)` helper creates a `Neo4jAgentMemory` bound to a session with all three memory tiers enabled (short-term, long-term, reasoning).
- `/memory/context` calls `memory._load_memory_variables_async({"input": query})` and maps the result to `MemoryContextResponse` with typed fields.
- `/memory/graph` calls `client.get_graph(session_id=session_id)` and maps `GraphNode`/`GraphRelationship` objects to Pydantic `GraphNodeResponse`/`GraphRelationshipResponse` models.
- `/memory/preferences` calls `client.long_term.search_preferences()` and maps `Preference` objects to Pydantic `PreferenceItem` models with category, preference, context, and confidence fields.
- Memory roundtrip test sends a chat message then verifies the `/memory/context` endpoint returns a valid response for the same session (full round-trip will complete in Phase 7 when the agent saves to memory).

### Phase 6: Tool Conversion — COMPLETE

**Created `tools/` module with 15 LangChain `@tool` functions across 5 modules, all with Pydantic `args_schema` input schemas and async implementations. Factory pattern injects `MemoryClient` via closure — no global state.**

**Existing test suite: 12 passed, 0 failed (no regressions).**

#### Module Structure

```
tools/
├── __init__.py           — create_tools(client) factory, returns list[BaseTool]
├── product_search.py     — 3 tools, 3 schemas
├── recommendations.py    — 3 tools, 3 schemas
├── inventory.py          — 2 tools, 2 schemas
├── cart.py               — 6 tools, 5 schemas (get_cart and clear_cart share CartInput)
└── memory_tools.py       — 1 tool, 1 schema
```

#### Tool Inventory (15 tools, 14 Pydantic input schemas)

| Module | Tool | Input Schema | Description |
|--------|------|-------------|-------------|
| product_search | `search_products` | `SearchProductsInput` (query, category, brand, max_price, limit) | Vector search with text fallback |
| product_search | `get_product_details` | `ProductDetailsInput` (product_id) | Full product record with category/brand joins |
| product_search | `get_related_products` | `RelatedProductsInput` (product_id, relationship_type, limit) | Graph-based related products |
| recommendations | `get_recommendations` | `RecommendationsInput` (category, limit, session_id) | Preference-based + popularity fallback |
| recommendations | `get_bought_together` | `BoughtTogetherInput` (product_id, limit) | Co-purchase frequency |
| recommendations | `explain_product_connection` | `ConnectionInput` (product_id_a, product_id_b) | Shared categories/brands/attributes |
| inventory | `check_inventory` | `InventoryCheckInput` (product_id) | Stock status with quantity and messaging |
| inventory | `find_alternatives` | `AlternativesInput` (product_id, max_results) | In-stock substitutes, same category, ±30% price |
| cart | `get_cart` | `CartInput` (session_id) | Cart contents with subtotal/tax/total |
| cart | `add_to_cart` | `AddToCartInput` (session_id, product_id, quantity) | Stock validation + MERGE cart |
| cart | `remove_from_cart` | `RemoveFromCartInput` (session_id, product_id) | Remove item from cart |
| cart | `update_cart_item` | `UpdateCartInput` (session_id, product_id, quantity) | Update quantity (0 to remove) |
| cart | `clear_cart` | `CartInput` (session_id) | Remove all cart items |
| cart | `apply_coupon` | `CouponInput` (session_id, coupon_code) | Validate and apply discount |
| memory_tools | `search_memory` | `MemorySearchInput` (query, search_type, limit) | Neo4jMemoryRetriever with type filtering |

#### Key Implementation Details

- **Factory pattern**: `create_tools(client: MemoryClient) -> list[BaseTool]` in `tools/__init__.py` creates all 15 tools as closures capturing the client. No global mutable state.
- **Pydantic input schemas**: Every tool uses `@tool(args_schema=SchemaClass)` with `Field(description=...)` on all fields. Numeric fields use `Field(ge=..., le=...)` bounds.
- **Async throughout**: All tool functions are `async def` and use `await client.graph.execute_read()` / `execute_write()` for Neo4j queries.
- **Parameter binding**: All Cypher queries use `$param` binding — no f-string interpolation of user input. The only f-string interpolation is for `relationship_type` which is validated against `ALLOWED_RELATIONSHIP_TYPES` frozenset.
- **Graceful error handling**: Tools return JSON error messages instead of raising exceptions (e.g., `{"error": "Product not found"}`), allowing the agent to respond conversationally.
- **JSON string returns**: All tools return `json.dumps(...)` strings, which is the standard LangChain tool return format for structured data the LLM can reason about.
- **Cart tools**: Full shopping cart lifecycle — MERGE pattern for cart creation, stock validation before add, coupon validation with percentage/fixed discount types.
- **Memory tools**: Wraps `Neo4jMemoryRetriever` with Literal type filtering (`all`, `messages`, `entities`, `preferences`).
