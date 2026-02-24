# Phase 2 Implementation Plan: Agentic Commerce — Memory and Learning

## Status: COMPLETE

All steps implemented. Ready for deployment and verification.

---

## Prerequisite — DONE

Knowledge tools were already wired into `ALL_TOOLS` in `react_agent.py` (confirmed during implementation — they were added in a prior session). No fix needed.

---

## Step 1: Add user_id to RetailContext — DONE

Added `user_id: str | None = None` field to `RetailContext` dataclass. This field scopes long-term memory and reasoning traces to a specific user, while `session_id` continues to scope short-term conversation memory to a single session.

**File**: `src/retail_context.py`

---

## Step 2: Pass user_id through the serving adapter — DONE

The serving adapter now extracts both `session_id` and `user_id` from `custom_inputs` and passes both into the `RetailContext` constructor. If no `user_id` is provided, it remains None.

**File**: `src/serving_adapter.py`

---

## Step 3: Turn on entity extraction in remember_message — DONE

Flipped `extract_entities=False` to `extract_entities=True` in `remember_message`. This activates the neo4j-agent-memory extraction pipeline, which automatically pulls Person, Organization, Location, and Object entities from conversation text and stores them in the knowledge graph with EXTRACTED_FROM relationships.

**File**: `src/memory_tools.py`

---

## Step 4: Add preference tracking tools to memory_tools — DONE

Added two new tools to `memory_tools.py`:

**track_preference** — Takes `preference_type` (brand, category, size, price_range, activity, material, style) and `preference_value`. Stores in long-term memory via `client.long_term.add_preference()`. Requires `user_id` — returns error if missing. Added to `MEMORY_TOOLS` export.

**get_user_profile** — Queries `client.long_term.search_preferences()` for all stored preferences for the current user. Returns structured summary with category, preference text, context, and confidence. Added to `MEMORY_TOOLS` export.

**File**: `src/memory_tools.py`

---

## Step 5: Create reasoning trace tools — DONE

Created `reasoning_tools.py` with two tools:

**record_reasoning_trace** — Takes task description, list of step dicts (thought/action/observation/tool_name), outcome, and success flag. Uses the full reasoning memory API: `client.reasoning.start_trace()` -> `add_step()` -> `record_tool_call()` -> `complete_trace()`. All steps and the task are embedded for future semantic search.

**recall_past_reasoning** — Takes a task description and uses `client.reasoning.get_similar_traces()` to find successful past traces by embedding similarity. Fetches full trace details including steps. Threshold 0.5, success_only=True.

Exported as `REASONING_TOOLS`.

**File**: `src/reasoning_tools.py` (new)

---

## Step 6: Create the personalized recommendation tool — DONE

Created `commerce_tools.py` with one tool:

**recommend_for_user** — Capstone tool combining preferences with knowledge graph:
1. Loads user preferences from `client.long_term.search_preferences()`
2. Builds composite query from preferences + explicit query
3. Embeds composite query via `client._embedder.embed()`
4. Runs VectorCypher search on `chunk_embedding` index, traversing through Chunk -> Product with features and known issues
5. Returns recommendations with product details, relevance scores, supporting context, features, and known issues
6. Falls back gracefully when no preferences or no user_id exist

Exported as `COMMERCE_TOOLS`.

**File**: `src/commerce_tools.py` (new)

---

## Step 7: Register all new tools in the agent — DONE

Updated `react_agent.py`:
- Added imports for `COMMERCE_TOOLS` and `REASONING_TOOLS`
- `ALL_TOOLS` now includes: echo + MEMORY_TOOLS + PRODUCT_SEARCH_TOOLS + KNOWLEDGE_TOOLS + REASONING_TOOLS + COMMERCE_TOOLS + DIAGNOSTICS_TOOLS
- Cleaned up unused imports (`ToolRuntime`, `RetailContext` no longer needed at module level)

**File**: `src/react_agent.py`

---

## Step 8: Expand the system prompt — DONE

Rewrote the system prompt in `react_agent.py` with six sections:
- **SESSION START**: Load user profile at session start if user_id present
- **TOOL SELECTION GUIDE**: Product tools vs knowledge tools (unchanged from Phase 1)
- **PREFERENCES**: When/how to call track_preference with examples
- **PERSONALIZED RECOMMENDATIONS**: Prefer recommend_for_user for returning users
- **REASONING TRACES**: recall_past_reasoning before multi-step tasks, record_reasoning_trace after
- **MEMORY**: Clear distinction between short-term (session-scoped) and long-term (user-scoped)

**File**: `src/react_agent.py`

---

## Step 9: Verify — PENDING

Not yet deployed or tested. Next steps:
- Deploy by running `step1_deploy_agent.py` on a Databricks cluster
- Run `step4_demo_agent.py` on a Databricks cluster for regression testing
- Test preference persistence across sessions with same `user_id`
- Test reasoning trace recording and recall
- Test `recommend_for_user` with and without stored preferences

---

## Files changed (summary)

| File | Change | Status |
|------|--------|--------|
| `src/retail_context.py` | Add `user_id` field | DONE |
| `src/serving_adapter.py` | Extract and pass `user_id` from `custom_inputs` | DONE |
| `src/memory_tools.py` | Flip `extract_entities` to True, add `track_preference` and `get_user_profile` | DONE |
| `src/reasoning_tools.py` | New file — `record_reasoning_trace`, `recall_past_reasoning` | DONE |
| `src/commerce_tools.py` | New file — `recommend_for_user` | DONE |
| `src/react_agent.py` | Import new tools, add to `ALL_TOOLS`, rewrite system prompt | DONE |

## Files not changed

- `step1_deploy_agent.py`, `step2_load_products.py`, `step3_load_graphrag.py`, `step4_demo_agent.py`, `step5_demo_retrievers.py` — untouched.
- `src/product_tools.py`, `src/knowledge_tools.py`, `src/diagnostics_tool.py`, `src/deploy_config.py`, `src/databricks_embedder.py` — untouched.
- Neo4j schema and data pipeline — untouched. Phase 2 uses the graph that already exists plus neo4j-agent-memory's built-in schema for long-term memory and reasoning traces.
- No new model endpoints or external service integrations.

## neo4j-agent-memory APIs used

| API | Where Used |
|-----|-----------|
| `client.long_term.add_preference(category, preference, context, generate_embedding)` | `track_preference` |
| `client.long_term.search_preferences(query, limit, threshold)` | `get_user_profile`, `recommend_for_user` |
| `client.reasoning.start_trace(session_id, task, generate_embedding)` | `record_reasoning_trace` |
| `client.reasoning.add_step(trace_id, thought, action, observation, generate_embedding)` | `record_reasoning_trace` |
| `client.reasoning.record_tool_call(step_id, tool_name, arguments, result, status, duration_ms)` | `record_reasoning_trace` |
| `client.reasoning.complete_trace(trace_id, outcome, success)` | `record_reasoning_trace` |
| `client.reasoning.get_similar_traces(task, limit, success_only, threshold)` | `recall_past_reasoning` |
| `client.reasoning.get_trace(trace_id)` | `recall_past_reasoning` |
| `client.short_term.add_message(..., extract_entities=True)` | `remember_message` (changed from False) |
