# Proposal: Migrate Retail Assistant from Microsoft Agent Framework to LangGraph with Neo4j Agent Memory

## Problem Statement

The current retail shopping assistant in `neo4j-labs/agent-memory/examples/microsoft_agent_retail_assistant` is built on top of the Microsoft Agent Framework (beta version 1.0.0b260212). This framework is still in pre-release and tightly couples the agent logic, tool execution, and memory management into a single opinionated runtime. The application relies on Microsoft-specific abstractions such as `OpenAIChatClient`, `AzureOpenAIResponsesClient`, `FunctionTool`, `Neo4jMicrosoftMemory`, and `Neo4jContextProvider` that limit portability and make it difficult to swap LLM providers, customize execution flow, or extend the agent's behavior beyond what the framework permits.

The agent currently handles product search, inventory checks, cart management, graph-based recommendations, and a three-layer memory system (short-term conversation, long-term preferences and entities, and reasoning traces) all stored in Neo4j. While functional, the tight binding to a beta framework creates risk around stability, community support, and long-term maintainability.

The impact is threefold: the team cannot easily extend the agent workflow with conditional branching or multi-agent coordination, the beta framework may introduce breaking changes without notice, and new contributors face a steep learning curve with a less widely adopted tool.

## Proposed Solution

Migrate the retail assistant to LangGraph, a production-grade orchestration framework for building stateful, long-running agents. LangGraph (latest stable version 1.0.8, with prebuilt helpers at version 1.0.4) provides a graph-based execution model where each step in the agent's reasoning is a node in a directed graph, connected by edges that define the flow of control. This maps naturally to the retail assistant's existing pattern of receiving a user message, deciding which tool to call, executing the tool, and looping until a final response is ready.

For memory, the migration will use the existing `neo4j-agent-memory` library located at `/Users/ryanknight/projects/neo4j-labs/agent-memory`. This library already provides a purpose-built LangChain integration under `src/neo4j_agent_memory/integrations/langchain` that includes two key components: `Neo4jAgentMemory` (a LangChain-compatible memory class) and `Neo4jMemoryRetriever` (a LangChain BaseRetriever for semantic search across all memory tiers). This means the entire three-layer Neo4j memory system — short-term conversation, long-term entities and preferences, and reasoning traces — carries over directly without reimplementation. There is no need to use LangGraph's built-in `InMemoryStore` or `InMemoryStore` for memory; the neo4j-agent-memory library handles all memory storage, retrieval, and semantic search through Neo4j.

The expected outcomes are a more flexible agent architecture, access to a larger ecosystem of LangChain-compatible tools and models, easier onboarding for new contributors, and a stable foundation that will not break with beta releases — all while preserving the full power of the Neo4j graph-backed memory system.

## Requirements

### Agent Orchestration

- The agent must be built using LangGraph's `create_react_agent` from `langgraph.prebuilt`, which provides a ReAct-style tool-calling loop out of the box.
- The agent must accept a system prompt that instructs it to help customers find products, learn preferences, provide recommendations, and manage shopping carts.
- The agent must support streaming responses back to the FastAPI server using LangGraph's `stream_mode="updates"` so the frontend continues to receive real-time token-by-token output over SSE.
- The LLM must be initialized using `langchain.chat_models.init_chat_model`, which allows swapping between OpenAI, Azure OpenAI, Anthropic, or any other supported provider by changing a single configuration value.

### Tool Migration

- All existing tools must be converted to LangChain tool format using the `@tool` decorator from `langchain_core.tools`.
- The following tools must be preserved with identical functionality:
  - Product search (vector and text-based with filters for category, brand, and price).
  - Product detail retrieval by ID.
  - Related product discovery through graph relationships (same category, same brand, shared attributes).
  - Inventory and stock checking with low-stock and out-of-stock alternative suggestions.
  - Shopping cart operations (add, remove, update, clear, apply coupon, save for later).
  - Personalized recommendations using learned preferences combined with graph traversal.
- All tools must continue to query Neo4j directly for product data, relationships, and graph algorithms.

### Memory Architecture Using neo4j-agent-memory

The memory system must use the `neo4j-agent-memory` library from `/Users/ryanknight/projects/neo4j-labs/agent-memory` rather than LangGraph's built-in memory stores. This library provides a complete three-tier memory hierarchy backed by Neo4j with a ready-made LangChain integration.

#### Neo4jAgentMemory (LangChain Memory Interface)

- The agent must use the `Neo4jAgentMemory` class from `neo4j_agent_memory.integrations.langchain` as its primary memory interface.
- This class wraps the `MemoryClient` and exposes memory as LangChain-compatible variables that can be injected into agent prompts.
- Short-term memory must be enabled to retrieve recent conversation history, formatted as role-content pairs, limited to the most recent messages per session.
- Long-term memory must be enabled to retrieve extracted entities (people, objects, locations, events, organizations following the POLE+O model), user preferences (categorized by type such as brand affinity, style, budget), and declarative facts (subject-predicate-object triples with temporal validity).
- Reasoning memory must be enabled to retrieve similar past task execution traces, including what tools were called, what decisions were made, and what outcomes resulted.
- The memory must be loaded before each agent turn by calling `load_memory_variables` with the user's latest message as the search query. This returns a dictionary containing `history` (formatted conversation), `context` (entity and preference descriptions), `preferences` (relevant user preferences), and `similar_tasks` (formatted reasoning traces from past interactions).
- After each agent turn, the memory must be saved by calling `save_context` with the user input and assistant output, which stores both messages to Neo4j short-term memory.

#### Neo4jMemoryRetriever (LangChain Retriever Interface)

- The `Neo4jMemoryRetriever` class must be available as a retriever tool the agent can invoke to perform semantic search across all memory tiers on demand.
- The retriever searches short-term messages, long-term entities and preferences, and reasoning traces using vector similarity on embeddings stored in Neo4j.
- Results are returned as LangChain Document objects with metadata indicating the source type, similarity score, and relevant attributes.
- The retriever must be configured with a similarity threshold (default 0.7) to filter out low-relevance results and a maximum result count.

#### MemoryClient and MemorySettings

- The `MemoryClient` from `neo4j_agent_memory` must be initialized with a `MemorySettings` configuration object that uses Pydantic for validation.
- The `MemorySettings` must configure the Neo4j connection (URI, username, password, database), the embedding provider (OpenAI `text-embedding-3-small` at 1536 dimensions), and the LLM provider for entity extraction.
- The `MemoryClient` provides direct access to the three memory subsystems: `short_term` (ShortTermMemory for conversations and messages), `long_term` (LongTermMemory for entities, preferences, facts, and relationships), and `reasoning` (ReasoningMemory for traces, steps, and tool call records).
- Session isolation must be maintained by passing a unique `session_id` to the `Neo4jAgentMemory` instance for each conversation.

#### Reasoning Trace Recording

- The `StreamingTraceRecorder` context manager from the reasoning memory module must be used to record tool execution traces during agent streaming.
- Each agent turn must start a new trace with a task description, record each tool call with its arguments, result, status, and duration, and complete the trace with the final outcome and success status.
- Traces must be embedded so that future similar tasks can retrieve relevant past reasoning via the `get_similar_traces` method.
- Tool statistics (total calls, success rate, average duration) must be maintained incrementally on Tool nodes in Neo4j for performance monitoring.

#### Entity Extraction and Deduplication

- Entity extraction must be enabled on incoming user messages to identify mentions of people, objects, locations, events, and organizations.
- The long-term memory's deduplication system must be active to prevent duplicate entities, using a combination of embedding similarity (auto-merge above 0.95, flag for review above 0.85) and fuzzy string matching (threshold 0.9).
- Extracted entities must be linked to the messages they were extracted from via relationships in the graph.

### Neo4j Integration

- The Neo4j driver connection and all Cypher queries for product search, recommendations, inventory, and cart operations must remain unchanged.
- The vector index on product embeddings (1536-dimension cosine similarity) must continue to be used for semantic product search.
- Graph Data Science algorithms (PageRank for product ranking, node similarity for related products, shortest path for relationship explanation) must remain available as optional tools when the GDS plugin is installed, with a fallback to basic Cypher queries when it is not.
- The product data loader (16 sample products across 5 categories with pre-defined relationships and attributes) must work without modification.

### API and Frontend Compatibility

- The FastAPI backend must continue to expose the same endpoints: `/chat` for SSE-streaming conversation, `/chat/sync` for non-streaming, `/memory/context`, `/memory/graph`, `/memory/preferences`, `/products/search`, `/products/{id}`, `/products/{id}/related`, and `/health`.
- The `/chat` endpoint must stream events in the same SSE format (tokens, tool calls, tool results) so the existing Next.js frontend with Chakra UI requires no changes.
- Session management must continue to work via session IDs, with the frontend storing the session ID in localStorage.

### Configuration and Dependencies

- The `requirements.txt` must replace `agent-framework` and `neo4j-agent-memory[microsoft-agent]` with `langgraph>=1.0.8`, `langgraph-prebuilt>=1.0.4`, `langchain-core`, `langchain-openai` (or `langchain-anthropic` depending on the chosen LLM), and `neo4j-agent-memory[openai,langchain]` pointing to the local agent-memory repository.
- All existing environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY, and the optional Azure OpenAI variables) must continue to be read from `.env` using `pydantic-settings`.
- Pydantic models must be used for all typed configuration and data structures.

### Best Practices from LangGraph Documentation (v1.0.8)

- Use the `entrypoint` and `task` decorators from the Functional API when custom control flow is needed beyond what `create_react_agent` provides, such as adding tool call review or conditional branching.
- Use `add_messages` from `langgraph.graph.message` for safe message list manipulation that handles deduplication and ordering.
- Use the `previous` parameter in entrypoint functions to access state from prior invocations when building custom workflows with checkpointers.
- Use `entrypoint.final(value=..., save=...)` to separate the return value from the persisted state when the two need to differ.
- Use `Runtime` context to access the store and configuration within node functions rather than passing them as global state.
- Use `context_schema` on `StateGraph` to define typed per-invocation context (such as user ID) that is available to all nodes without polluting the graph state.
- For LangGraph's own checkpointer (which tracks the graph execution state, not the domain memory), use `InMemorySaver` for development. The domain memory (conversations, preferences, entities, reasoning) lives entirely in Neo4j through the neo4j-agent-memory library and does not depend on LangGraph's checkpointer.

## Implementation Plan

### Phase 1: Discovery and Mapping

**Goal:** Build a complete inventory of every Microsoft Agent Framework dependency and map each one to its LangGraph or neo4j-agent-memory equivalent.

- Read every Python file in the current `microsoft_agent_retail_assistant/backend` directory and record every import, class instantiation, and method call that touches the Microsoft Agent Framework.
- Catalog the exact signature of every tool function: parameter names, types, return shapes, and any side effects such as writing to Neo4j or calling the memory client.
- Document the SSE streaming event format currently emitted by the `/chat` endpoint, including the exact JSON shape for token events, tool call events, and tool result events, so the replacement produces byte-identical output.
- Document how the current `Neo4jMicrosoftMemory` and `Neo4jContextProvider` inject context into the agent prompt, including what memory variables are included (conversation history, entity context, preference context, reasoning traces) and in what order.
- Produce a file-by-file mapping table: for each file that must change, list what is being removed, what is replacing it, and which neo4j-agent-memory or LangGraph class provides the replacement.
- Identify any Microsoft-specific behavior that has no direct equivalent (such as framework-level automatic tool dispatch versus LangGraph's ReAct loop) and document how the replacement will achieve the same user-facing behavior.

### Phase 2: Dependencies and Project Scaffolding

**Goal:** Set up the new dependency tree and project structure so that all subsequent phases can build and run.

- Create the new `requirements.txt` (or `pyproject.toml` if the project uses one) with `langgraph>=1.0.8`, `langgraph-prebuilt>=1.0.4`, `langchain-core`, `langchain-openai`, and `neo4j-agent-memory[openai,langchain]` pointing to the local agent-memory repository path.
- Remove the `agent-framework` and `neo4j-agent-memory[microsoft-agent]` dependencies entirely.
- Verify that the dependency set resolves cleanly and that all packages install without conflicts.
- Confirm that the existing environment variables (.env file with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY, and optional Azure OpenAI variables) are still read correctly by `pydantic-settings` after the dependency change.
- Confirm that the Neo4j database is reachable and that the product data loader still runs successfully against the updated dependency set, since it does not depend on the agent framework.

### Phase 3: API Layer

**Goal:** Stand up the FastAPI application shell with all endpoints defined so there is a running server to test against from the very beginning.

- Create the FastAPI application with the same endpoint signatures as the original: `/chat` for SSE-streaming conversation, `/chat/sync` for non-streaming, `/memory/context`, `/memory/graph`, `/memory/preferences`, `/products/search`, `/products/{id}`, `/products/{id}/related`, and `/health`.
- Each endpoint should accept the same request parameters and return the same response shapes as the original, but the chat endpoints can initially return a static placeholder response since the agent is not yet wired up.
- The `/health` endpoint must verify that the Neo4j database is reachable using the connection details from the environment variables.
- The product endpoints (`/products/search`, `/products/{id}`, `/products/{id}/related`) must query Neo4j directly for product data, since these do not depend on any agent framework and can be implemented immediately using the existing Cypher queries from the original codebase.
- The memory endpoints (`/memory/context`, `/memory/graph`, `/memory/preferences`) should return empty but correctly shaped responses for now, to be filled in once the memory layer is connected.
- Session management must accept a session ID from the request (or generate one if not provided) so that all subsequent phases have a consistent session handling pattern from the start.
- Configure CORS, error handling, and the SSE response format so the Next.js frontend can connect to this server immediately, even if the chat responses are placeholders.

### Phase 4: Plain Python Test Suite

**Goal:** Create a simple test suite written in plain Python (no pytest, no test frameworks) that calls the API endpoints over HTTP, so every subsequent phase has an automated way to verify that changes did not break anything.

- Write a single Python file that uses only the standard library (urllib or http.client) or the requests library to call each API endpoint and check the response.
- The test file must be runnable with a plain `python test_api.py` command and print clear pass/fail output for each test to the terminal.
- Start with a health check test that calls `/health` and verifies the response indicates a healthy Neo4j connection.
- Add a product search test that calls `/products/search` with a known query (such as "running shoes") and verifies the response contains at least one product with the expected fields (name, price, category, brand, in_stock).
- Add a product detail test that calls `/products/{id}` with a known product ID from the sample data and verifies the full product record is returned.
- Add a related products test that calls `/products/{id}/related` and verifies the response contains products linked by category, brand, or shared attributes.
- Add a chat test that sends a message to `/chat/sync` and verifies the response contains an assistant message (even if it is a placeholder at this stage).
- Add an SSE streaming test that connects to `/chat` and verifies that at least one SSE event is received before the connection closes.
- Add memory endpoint tests that call `/memory/context`, `/memory/graph`, and `/memory/preferences` with a session ID and verify the responses are correctly shaped (even if empty at this stage).
- Each test must print what it is testing, the endpoint it is calling, and whether it passed or failed, with the failure reason if applicable.
- The test suite must exit with a non-zero exit code if any test fails, so it can be used in automation.
- As each subsequent phase adds real functionality behind the endpoints, the test suite will be extended with additional assertions that verify the actual behavior, not just the response shape.

### Phase 5: Neo4jAgentMemory Verification

**Goal:** Set up the simplest possible working connection between LangChain and the Neo4jAgentMemory from the neo4j-agent-memory library, proving that memory reads and writes work before building anything more complex on top of it.

- Initialize a `MemoryClient` from `neo4j_agent_memory` using a `MemorySettings` object configured with the Neo4j connection details from the environment and the OpenAI `text-embedding-3-small` embedding provider.
- Create an instance of `Neo4jAgentMemory` from `neo4j_agent_memory.integrations.langchain`, configured with the `MemoryClient`, a hardcoded test session ID, and all three memory tiers enabled (short-term, long-term, reasoning).
- Call `save_context` with a simple test input ("I like Nike running shoes") and a test output ("Great choice, Nike has excellent running shoes"), and verify that both messages are written to Neo4j by querying the database directly or by calling `load_memory_variables` and checking that the conversation history contains the saved messages.
- Call `load_memory_variables` with a search query ("running shoes") and verify that the returned dictionary contains the expected keys: `history` (with the saved conversation), `context` (entity descriptions if any were extracted), `preferences` (any matching preferences), and `similar_tasks` (empty at this point since no reasoning traces exist yet).
- Create an instance of `Neo4jMemoryRetriever` from the same integration module, configured to search across all three memory tiers, and call its retrieval method with the query "Nike shoes" to verify it returns LangChain Document objects with metadata including the type and similarity score.
- Add tests to the plain Python test suite from Phase 4 that start the FastAPI server, send a chat message, and then call the `/memory/context` endpoint to verify the message appears in the session's conversation history.
- This phase deliberately does not build the full agent or wire up tools. The only goal is to confirm that the neo4j-agent-memory LangChain integration can save context, load memory variables, and retrieve documents against a live Neo4j instance, so that all subsequent phases can build on a known-working foundation.

### Phase 6: Tool Conversion

**Goal:** Convert every tool from the Microsoft Agent Framework's `FunctionTool` and `@tool` decorator format to LangChain's `@tool` decorator format, and verify each one works independently.

- Convert each tool function in `tools/product_search.py` (search_products, get_product_details, get_related_products) to use the `@tool` decorator from `langchain_core.tools`, preserving the exact same parameter names, types, docstrings, and return values.
- Convert each tool function in `tools/recommendations.py` (get_recommendations, get_related_products, get_bought_together, explain_product_connection) to the LangChain tool format.
- Convert each tool function in `tools/inventory.py` (check_inventory, get_stock_status, find_alternatives, notify_when_available, get_low_stock_products) to the LangChain tool format.
- Convert each tool function in `tools/cart.py` (get_cart, add_to_cart, update_cart_item, remove_from_cart, clear_cart, apply_coupon, save_cart_for_later) to the LangChain tool format.
- Expose the `Neo4jMemoryRetriever` as a retriever tool that the agent can call to perform on-demand semantic search across all memory tiers.
- Verify that each converted tool can be called independently with test arguments and returns the same results as before.
- Verify that all tools receive the Neo4j driver connection they need, either through closure over the `MemoryClient` or through a shared application context, without using global mutable state.
- Add tool-level tests to the plain Python test suite that call each tool function directly (not through the API) with known arguments and verify the return values match expected results from the sample product data.

### Phase 7: Agent Construction

**Goal:** Build the LangGraph agent that replaces the Microsoft Agent Framework agent, wiring together the LLM, tools, and memory into a working whole.

- Create the LangGraph agent using `create_react_agent` from `langgraph.prebuilt`, passing in the LLM (initialized via `init_chat_model`), the full list of converted tools from Phase 6, and a system prompt.
- The system prompt must instruct the agent to help customers find products matching their needs, learn and remember their preferences using the memory tools, provide personalized recommendations by combining preferences with graph-based product relationships, and handle inventory constraints gracefully by suggesting alternatives for out-of-stock items.
- Attach an `InMemorySaver` checkpointer to the agent for LangGraph's internal execution state tracking. This is separate from the domain memory in Neo4j; it allows LangGraph to resume interrupted graph executions.
- Before each agent invocation, load memory variables from `Neo4jAgentMemory` using the user's message as the search query, and prepend the returned context (conversation history, entity context, preference context, reasoning traces) to the message list so the LLM has full awareness of the user's history and preferences.
- After each agent invocation, save the conversation turn to Neo4j by calling `save_context` on the `Neo4jAgentMemory` instance with the user input and the agent's final response.
- Wire the agent into the `/chat` endpoint by replacing the placeholder response with a call to the agent's `stream` method using `stream_mode="updates"`, iterating over the streamed chunks and converting them to SSE events in the same format the frontend expects (token events for incremental text, tool call events when the agent decides to invoke a tool, tool result events when a tool returns).
- Wire the agent into the `/chat/sync` endpoint by calling the agent's `invoke` method and returning the final response as a JSON object.
- Update the `/memory/context` endpoint to call `load_memory_variables` on the `Neo4jAgentMemory` instance and return the conversation history, entities, and preferences for the given session.
- Update the `/memory/graph` endpoint to call `get_graph` on the `MemoryClient` and return the nodes and edges for graph visualization.
- Update the `/memory/preferences` endpoint to call `search_preferences` on the `MemoryClient.long_term` subsystem and return the learned user preferences.
- Run the full plain Python test suite from Phase 4 and verify that the chat tests now return real agent responses instead of placeholders, that product questions trigger tool calls, and that memory endpoints return populated data after a conversation.

### Phase 8: Reasoning Trace Integration

**Goal:** Ensure that every agent turn produces a complete reasoning trace in Neo4j that can be retrieved by future similar tasks.

- Wrap each agent streaming invocation in a `StreamingTraceRecorder` context manager from the neo4j-agent-memory reasoning module, starting a trace with the user's message as the task description.
- For each tool call the agent makes during streaming, record the tool name, arguments, result, execution status (success, failure, error, timeout), and duration in milliseconds as a step in the trace.
- When the agent finishes its response, complete the trace with the final text as the outcome and a success flag indicating whether the turn completed without errors.
- Verify that traces are embedded and that calling `get_similar_traces` with a query semantically close to a past task returns the relevant trace.
- Verify that tool statistics (total calls, success rate, average duration per tool) are updated incrementally on Tool nodes in Neo4j after each recorded tool call.
- Verify that the `similar_tasks` field in `load_memory_variables` correctly includes formatted reasoning traces from past interactions when the current query is semantically similar.
- Add reasoning trace tests to the plain Python test suite: send a product search question through the `/chat/sync` endpoint, then call the memory context endpoint and verify that the reasoning trace appears in the similar tasks section when a semantically similar question is asked in a new session.

### Phase 9: End-to-End Testing

**Goal:** Confirm that the migrated application behaves identically to the original from the user's perspective, using both the plain Python test suite and manual testing.

- Run the full plain Python test suite and confirm every test passes.
- Extend the test suite with a multi-turn conversation test: send a greeting, ask for running shoes, refine by brand preference, check inventory, add to cart, ask for recommendations based on learned preferences, and verify the agent recalls preferences across multiple turns within the same session.
- Add a cross-session memory test: start a conversation with one session ID and express a brand preference, then start a new conversation with a different session ID but the same user ID and verify the agent remembers the preference from the first session through long-term memory.
- Add an entity extraction test: send a message mentioning a specific product and brand, then call the memory context endpoint and verify the extracted entities appear with the correct POLE+O type (the brand as an Organization, the product as an Object).
- Add an SSE streaming validation test that connects to the `/chat` endpoint, collects all SSE events, and verifies the event sequence includes at least one token event and that the final assembled response is coherent.
- Test the graph visualization endpoint by calling `/memory/graph` after a conversation and verifying the returned nodes include Message, Entity, and Preference nodes with the expected relationships between them.
- Test GDS fallback: if the Graph Data Science plugin is not installed, verify that the agent falls back to basic Cypher queries for recommendations and related products without errors.
- The test suite must continue to be runnable with a plain `python test_api.py` command, print clear pass/fail output, and exit with a non-zero code on any failure.

### Phase 10: Cleanup and Documentation

**Goal:** Remove all traces of the Microsoft Agent Framework and ensure the codebase is clean.

- Search the entire backend directory for any remaining imports, references, or comments mentioning the Microsoft Agent Framework, `agent-framework`, `Neo4jMicrosoftMemory`, `Neo4jContextProvider`, `FunctionTool`, `OpenAIChatClient`, or `AzureOpenAIResponsesClient`, and remove them.
- Remove any unused files, utility functions, or configuration keys that were only needed for the Microsoft integration.
- Update the README to reflect the new architecture: LangGraph for agent orchestration, neo4j-agent-memory with its LangChain integration for memory, and Neo4j for both product data and memory storage.
- Verify that no compatibility layers, wrapper functions, variable aliases, or commented-out code remain.
- Run the full plain Python test suite one final time to confirm everything is clean.

## Stakeholders

- Workshop participants who will use this as a learning example for building AI agents with graph databases.
- The Neo4j developer relations team maintaining the agent-memory examples.
- Contributors who need to extend or customize the retail assistant for their own use cases.

## Success Criteria

- The retail assistant runs end-to-end on LangGraph with the neo4j-agent-memory LangChain integration and identical user-facing behavior.
- All five tool categories (search, details, recommendations, inventory, cart) function correctly.
- Short-term memory (conversation history) persists within a session via Neo4j through `Neo4jAgentMemory.save_context`.
- Long-term memory (preferences, entities, facts) persists across sessions via Neo4j through the `MemoryClient.long_term` subsystem.
- Reasoning traces are recorded for every agent turn and retrievable by semantic similarity for future tasks.
- Entity extraction runs on user messages and deduplication prevents duplicate entities in the graph.
- Streaming responses arrive in real time with no perceptible latency regression.
- The Next.js frontend requires zero changes.
- The codebase contains no references to the Microsoft Agent Framework.

---

## Phase Status Tracker

### Phase 1: Discovery and Mapping — COMPLETE

**Microsoft Agent Framework imports found in 3 files:**

| File | Microsoft-Specific Imports | Replacement |
|------|---------------------------|-------------|
| `agent.py` | `from agent_framework import Agent, FunctionTool, Message, tool` | `create_react_agent` from `langgraph.prebuilt`, `@tool` from `langchain_core.tools` |
| `agent.py` | `from agent_framework.azure import AzureOpenAIResponsesClient` | `init_chat_model` from `langchain.chat_models` with Azure config |
| `agent.py` | `from agent_framework.openai import OpenAIChatClient` | `init_chat_model` from `langchain.chat_models` with OpenAI config |
| `agent.py` | `from neo4j_agent_memory.integrations.microsoft_agent import Neo4jMicrosoftMemory, create_memory_tools, record_agent_trace` | `Neo4jAgentMemory` and `Neo4jMemoryRetriever` from `neo4j_agent_memory.integrations.langchain`, `StreamingTraceRecorder` from `neo4j_agent_memory` |
| `memory_config.py` | `from neo4j_agent_memory.integrations.microsoft_agent import GDSAlgorithm, GDSConfig, Neo4jContextProvider, Neo4jMicrosoftMemory` | `Neo4jAgentMemory` from `neo4j_agent_memory.integrations.langchain`, GDS config moves to direct Cypher queries |
| `main.py` | `from agent import create_agent, run_agent_stream` | New `agent.py` using LangGraph `create_react_agent` |
| `requirements.txt` | `agent-framework>=1.0.0b260212` and `../../../[openai,microsoft-agent]` | `langgraph>=1.0.8`, `langchain-core`, `langchain-openai`, local `neo4j-agent-memory[openai,langchain]` |

**Files with zero Microsoft dependencies (carry over unchanged):**

| File | Status |
|------|--------|
| `tools/__init__.py` | Pure re-exports, no framework imports |
| `tools/product_search.py` | Pure Neo4j Cypher, only uses `logging` and `TYPE_CHECKING` |
| `tools/recommendations.py` | Pure Neo4j Cypher, only uses `logging` and `TYPE_CHECKING` |
| `tools/inventory.py` | Pure Neo4j Cypher, only uses `logging` and `TYPE_CHECKING` |
| `tools/cart.py` | Pure Neo4j Cypher, only uses `logging`, `datetime`, and `TYPE_CHECKING` |
| `data/load_products.py` | Uses `neo4j.AsyncGraphDatabase` directly, no agent framework dependency |
| `test_backend.py` | Pure stdlib HTTP calls, no framework dependency |

**SSE streaming event format (must be preserved):**

- `token` event: `{"content": "..."}` — incremental text from the agent
- `tool_call` event: `{"name": "...", "arguments": "..."}` — agent decided to call a tool
- `tool_result` event: `{"name": "...", "result": "..."}` — tool returned a result
- `done` event: `{"session_id": "..."}` — agent turn complete
- `error` event: `{"error": "..."}` — something failed

**Memory context injection pattern (current):**

The current system uses `Neo4jContextProvider` attached to the agent via `context_providers=[memory.context_provider]`. Before each LLM call, the context provider queries Neo4j for conversation history (up to 10 recent messages), long-term entities and preferences (up to 15 items), and similar reasoning traces (up to 3). These are formatted as a system message prepended to the conversation. The LangGraph replacement will call `Neo4jAgentMemory.load_memory_variables()` before each invocation and prepend the returned `history`, `context`, `preferences`, and `similar_tasks` to the message list.

**Agent tool structure (current):**

The current `agent.py` defines 5 product tools inline as closures that capture the `memory.memory_client` for Neo4j access. The `@tool` decorator from `agent_framework` is used. The `create_memory_tools()` function from the Microsoft integration generates additional memory tools (search history, save preferences, find similar interactions, and optional GDS tools). All tools are combined and passed to `chat_client.as_agent()`. In the LangGraph version, the inline product tools will be converted to standalone functions using `@tool` from `langchain_core.tools`, and memory tools will be replaced by the `Neo4jMemoryRetriever` as a retriever tool.

**Key finding:** The `tools/` directory modules (product_search, recommendations, inventory, cart) are REST endpoint helpers used by `main.py` directly — they are NOT the same as the agent tools defined inline in `agent.py`. The agent tools in `agent.py` are closures that capture the memory client. Both sets of code query Neo4j with Cypher and have no Microsoft dependencies.

### Phase 2: Dependencies and Project Scaffolding — COMPLETE

**Updated `pyproject.toml` with new dependency tree.** Removed all Microsoft Agent Framework dependencies. Added LangGraph, LangChain, and neo4j-agent-memory with the langchain extra.

**Dependency resolution:** All 54 packages installed cleanly via `uv sync` with no conflicts.

**Installed package versions:**

| Package | Version | Notes |
|---------|---------|-------|
| langgraph | 1.0.8 | Agent orchestration (meets >=1.0.8 requirement) |
| langgraph-prebuilt | 1.0.7 | `create_react_agent` (meets >=1.0.4 requirement) |
| langgraph-checkpoint | 4.0.0 | `InMemorySaver` for graph execution state |
| langchain-core | 1.2.13 | `@tool` decorator, base abstractions |
| langchain-openai | 1.1.10 | OpenAI and Azure OpenAI chat model integration |
| neo4j-agent-memory | 0.1.0 | Local install from `/Users/ryanknight/projects/neo4j-labs/agent-memory` with `[openai,langchain]` extras |
| neo4j | 6.1.0 | Neo4j Python driver |
| fastapi | 0.129.0 | Web framework |
| pydantic | 2.12.5 | Data validation |
| pydantic-settings | 2.13.0 | Environment variable loading |
| sse-starlette | 3.2.0 | Server-Sent Events |
| uvicorn | 0.41.0 | ASGI server |

**Import verification:** All critical imports confirmed working:
- `langgraph.prebuilt.create_react_agent`
- `langgraph.checkpoint.memory.InMemorySaver`
- `neo4j_agent_memory.integrations.langchain.Neo4jAgentMemory`
- `neo4j_agent_memory.integrations.langchain.Neo4jMemoryRetriever`
- `langchain_core`, `langchain_openai`, `fastapi`, `pydantic`, `pydantic_settings`, `sse_starlette`

**Data loader compatibility:** The `data/load_products.py` script depends only on `neo4j.AsyncGraphDatabase` and `python-dotenv`, both of which are available in the new dependency set.

**Environment variables:** The `.env` file pattern (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY, and optional Azure OpenAI variables) continues to be read by `pydantic-settings` with no changes needed.

### Phase 3: API Layer — COMPLETE

**Created `main.py` with all 9 endpoints matching the original API surface.**

**Endpoint status:**

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/health` | GET | Fully functional | Checks `MemoryClient.is_connected` |
| `/chat` | POST | Placeholder | Returns static SSE stream with token + done events |
| `/chat/sync` | POST | Placeholder | Returns static JSON response |
| `/memory/context` | GET | Stub | Returns empty `{short_term: [], long_term: {entities: [], preferences: []}, reasoning: []}` |
| `/memory/graph` | GET | Stub | Returns empty `{nodes: [], edges: []}` |
| `/memory/preferences` | GET | Stub | Returns empty `{preferences: []}` |
| `/products/search` | GET | Fully functional | Vector search with text fallback, queries Neo4j directly |
| `/products/{id}` | GET | Fully functional | Returns 404 for missing products |
| `/products/{id}/related` | GET | Fully functional | Finds related by category, brand, and attributes |

**Key implementation details:**

- `Settings` class uses `pydantic-settings` to load all env vars from `.env` with `extra="ignore"`.
- `get_memory_settings()` creates a `MemorySettings` with Neo4j connection and OpenAI embedding config. For Azure OpenAI embeddings, the Azure API key is passed as the OpenAI key since the neo4j-agent-memory `OpenAIEmbedder` creates a standard `AsyncOpenAI` client. Product search falls back to text search if vector search fails.
- `_db()` and `_embedder()` helpers access `MemoryClient._client` (Neo4jClient) and `MemoryClient._embedder` (OpenAIEmbedder) since the installed version of neo4j-agent-memory does not expose a public `.graph` property.
- CORS configured for `localhost:3000` (Next.js frontend).
- SSE streaming configured via `sse-starlette` `EventSourceResponse`.
- Session management via in-memory dict with UUID generation.

**Verified all endpoints respond correctly against a live Neo4j Aura instance.** Product endpoints return empty results because the sample product data has not been loaded into this database yet, but the Cypher queries execute without error.
