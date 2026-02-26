# Phase 2 Implementation Plan: Agentic Commerce — Memory and Learning

## Status: COMPLETE (refactored)

All steps implemented. Post-implementation review identified and fixed four issues: a missing import bug, a user-isolation gap in preferences, duplicated preference-fetching logic, and a structural split to separate short-term from long-term memory tools.

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

## Step 4: Add preference tracking tools — DONE (refactored)

Created `preference_tools.py` with two tools (originally in `memory_tools.py`, split out during review):

**track_preference** — Takes `preference_type` and `preference_value`. Stores in long-term memory via `store_user_preference()` helper which attaches `user_id` in metadata for isolation. Requires `user_id` — returns error if missing.

**get_user_profile** — Retrieves preferences via `get_user_preferences()` helper which filters by `user_id` in metadata. Returns structured summary with category, preference text, context, and confidence.

Exported as `PREFERENCE_TOOLS`.

**File**: `src/preference_tools.py` (new)

---

## Step 5: Create reasoning trace tools — DONE

Created `reasoning_tools.py` with two tools:

**record_reasoning_trace** — Takes task description, list of step dicts (thought/action/observation/tool_name), outcome, and success flag. Uses the full reasoning memory API: `client.reasoning.start_trace()` -> `add_step()` -> `record_tool_call()` -> `complete_trace()`. All steps and the task are embedded for future semantic search.

**recall_past_reasoning** — Takes a task description and uses `client.reasoning.get_similar_traces()` to find successful past traces by embedding similarity. Fetches full trace details including steps. Threshold 0.5, success_only=True.

Exported as `REASONING_TOOLS`.

**File**: `src/reasoning_tools.py` (new)

---

## Step 6: Create the personalized recommendation tool — DONE (refactored)

Created `commerce_tools.py` with one tool:

**recommend_for_user** — Capstone tool combining preferences with knowledge graph:
1. Loads user preferences via shared `get_user_preferences()` helper (user-scoped)
2. Builds composite query from preferences + explicit query
3. Embeds composite query via `client._embedder.embed()`
4. Runs VectorCypher search on `chunk_embedding` index, traversing through Chunk -> Product with features and known issues
5. Returns recommendations with product details, relevance scores, supporting context, features, and known issues
6. Falls back gracefully when no preferences or no user_id exist

Exported as `COMMERCE_TOOLS`.

**File**: `src/commerce_tools.py` (new)

---

## Step 7: Register all new tools in the agent — DONE (refactored)

Updated `react_agent.py`:
- Imports: `MEMORY_TOOLS`, `PREFERENCE_TOOLS`, `PRODUCT_SEARCH_TOOLS`, `KNOWLEDGE_TOOLS`, `REASONING_TOOLS`, `COMMERCE_TOOLS`, `DIAGNOSTICS_TOOLS`
- `ALL_TOOLS`: echo + MEMORY_TOOLS + PREFERENCE_TOOLS + PRODUCT_SEARCH_TOOLS + KNOWLEDGE_TOOLS + REASONING_TOOLS + COMMERCE_TOOLS + DIAGNOSTICS_TOOLS
- `RetailContext` import restored (needed for `context_schema`)

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

## Post-Implementation Review Fixes

Four issues identified and fixed after initial implementation:

### Fix 1: Missing RetailContext import (bug)
`RetailContext` was removed from `react_agent.py` during an unused-import cleanup, but it is still needed on line 114 for `context_schema=RetailContext`. Restored the import.

### Fix 2: User preference isolation (critical correctness)
The agent-memory library's `add_preference()` and `search_preferences()` have no built-in user_id scoping — preferences are stored globally in Neo4j. Without metadata tagging, all users would share the same preference pool.

**Solution**: Created `memory_helpers.py` with two functions:
- `store_user_preference()` — passes `metadata={"user_id": user_id}` when storing
- `get_user_preferences()` — fetches broadly then filters client-side by `user_id` in metadata

Both `preference_tools.py` and `commerce_tools.py` now use these helpers.

### Fix 3: Duplicated preference-fetching logic (DRY)
The same `search_preferences(query="user preferences", limit=20, threshold=0.0)` + filter pattern appeared in both `get_user_profile` and `recommend_for_user`. Extracted to the shared `get_user_preferences()` helper in `memory_helpers.py`.

### Fix 4: Structural split (modularity)
`memory_tools.py` was mixing two concerns: session-scoped short-term memory (remember/recall/search) and user-scoped long-term preferences (track/profile). Split into:
- `memory_tools.py` — short-term only (`MEMORY_TOOLS`: 3 tools)
- `preference_tools.py` — long-term preferences (`PREFERENCE_TOOLS`: 2 tools)
- `memory_helpers.py` — shared user-scoped preference helpers (no tools, just functions)

---

## Files changed (summary)

| File | Change | Status |
|------|--------|--------|
| `src/retail_context.py` | Add `user_id` field | DONE |
| `src/serving_adapter.py` | Extract and pass `user_id` from `custom_inputs` | DONE |
| `src/memory_tools.py` | Flip `extract_entities` to True, remove preference tools (moved out) | DONE |
| `src/memory_helpers.py` | New file — shared `store_user_preference`, `get_user_preferences` helpers | DONE |
| `src/preference_tools.py` | New file — `track_preference`, `get_user_profile` (user-scoped) | DONE |
| `src/reasoning_tools.py` | New file — `record_reasoning_trace`, `recall_past_reasoning` | DONE |
| `src/commerce_tools.py` | New file — `recommend_for_user` (uses shared helpers) | DONE |
| `src/react_agent.py` | Import all tool lists, add to `ALL_TOOLS`, rewrite system prompt | DONE |

## Files not changed

- `step1_deploy_agent.py`, `step2_load_products.py`, `step3_load_graphrag.py`, `step4_demo_agent.py`, `step5_demo_retrievers.py` — untouched.
- `src/product_tools.py`, `src/knowledge_tools.py`, `src/diagnostics_tool.py`, `src/deploy_config.py`, `src/databricks_embedder.py` — untouched.
- Neo4j schema and data pipeline — untouched. Phase 2 uses the graph that already exists plus neo4j-agent-memory's built-in schema for long-term memory and reasoning traces.
- No new model endpoints or external service integrations.

## neo4j-agent-memory APIs used

| API | Where Used |
|-----|-----------|
| `client.long_term.add_preference(category, preference, context, generate_embedding, metadata)` | `memory_helpers.store_user_preference` |
| `client.long_term.search_preferences(query, limit, threshold)` | `memory_helpers.get_user_preferences` |
| `client.reasoning.start_trace(session_id, task, generate_embedding)` | `record_reasoning_trace` |
| `client.reasoning.add_step(trace_id, thought, action, observation, generate_embedding)` | `record_reasoning_trace` |
| `client.reasoning.record_tool_call(step_id, tool_name, arguments, result, status, duration_ms)` | `record_reasoning_trace` |
| `client.reasoning.complete_trace(trace_id, outcome, success)` | `record_reasoning_trace` |
| `client.reasoning.get_similar_traces(task, limit, success_only, threshold)` | `recall_past_reasoning` |
| `client.reasoning.get_trace(trace_id)` | `recall_past_reasoning` |
| `client.short_term.add_message(..., extract_entities=True)` | `remember_message` (changed from False) |

## Tool architecture

```
react_agent.py (ALL_TOOLS)
├── memory_tools.py        — MEMORY_TOOLS (3): remember, recall, search  [session-scoped]
├── preference_tools.py    — PREFERENCE_TOOLS (2): track, profile        [user-scoped]
│   └── memory_helpers.py  — store_user_preference, get_user_preferences [user isolation]
├── product_tools.py       — PRODUCT_SEARCH_TOOLS (3): search, details, related
├── knowledge_tools.py     — KNOWLEDGE_TOOLS (3): knowledge, hybrid, diagnose
├── reasoning_tools.py     — REASONING_TOOLS (2): record, recall         [user-scoped]
├── commerce_tools.py      — COMMERCE_TOOLS (1): recommend_for_user      [user-scoped]
│   └── memory_helpers.py  — get_user_preferences                        [shared helper]
└── diagnostics_tool.py    — DIAGNOSTICS_TOOLS
```
