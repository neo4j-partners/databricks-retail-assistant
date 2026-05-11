# Real Backend Integration Plan

## Goal

Make the demo client a real backend-backed Databricks App instead of a sample-data presentation shell.

The finished demo should send browser requests to the demo-client FastAPI backend, have that backend call the deployed retail agent endpoint, and render live agent results whenever the endpoint is available. Sample data should remain only as an explicit development or fallback mode.

This document is now the source of truth for the remaining work. The older demo proposal and backend gap documents are historical context only.

## Current State

- Status: In progress
- The retail agent has real Neo4j catalog search tools.
- The retail agent has GraphRAG knowledge tools for vector search, hybrid search, and product issue diagnosis.
- The retail agent has long-term preference tools and a personalized recommendation tool.
- The retail agent serving adapter has source code that can return structured demo trace metadata from real LangGraph tool calls.
- The demo-client backend has search and diagnosis routes that can call the `agents_retail_assistant-retail-retail_agent_v3` Databricks Model Serving endpoint.
- The generated frontend API client includes search and diagnosis calls.
- The visible React demo now submits through the generated backend API client.
- Live endpoint behavior, deployed app permissions, and real trace rendering have not been validated end to end.

## Assumptions

- The browser must never call Databricks Model Serving directly.
- The backend remains the boundary for Databricks authentication, response normalization, fallback behavior, and logging.
- The first production-worthy demo keeps the two existing tabs: Agentic Search and Issue Diagnosis.
- Sample data remains available for local development and explicitly enabled fallback, but live mode must be the normal path.
- The canonical deployed endpoint name is `agents_retail_assistant-retail-retail_agent_v3`.
- Reset remains browser-local unless a scoped server-side memory reset capability is deliberately added later.

## Risks

- The React app may look live while still using sample data unless the local sample helper is removed from the submit path.
- The serving endpoint may be running an older model version that does not include structured demo trace metadata.
- The agent may answer in prose without calling the tools needed for product cards, knowledge chunks, recommendations, or trace rows.
- The app service principal may not have permission to query the serving endpoint after deployment.
- Long-term preference and reasoning behavior may persist between sessions unless user ids are scoped deliberately for demos.
- The recommendation tool output is real upstream, but it is not yet normalized into the demo trace contract.
- Local environment files may contain secrets. They must not be promoted into tracked docs, samples, logs, or build artifacts.

## Phase Checklist

### Phase 1: Make The Frontend Use The Backend

- Status: Complete
- Outcome: Submitting either demo tab calls the generated backend API client instead of local sample data.
- Checklist:
  - Complete: Replace the active submit path in the React route with the generated search and diagnosis API calls.
  - Complete: Keep the existing UI response shape by adding a frontend adapter from backend response fields to display fields.
  - Complete: Preserve preset buttons by passing preset ids to the backend instead of selecting local samples in the browser.
  - Complete: Preserve session id handling by sending the current session id to the backend and storing the returned effective session id.
  - Complete: Add user-visible warnings when the backend reports sample, fallback, inferred, or unavailable trace data.
  - Complete: Remove the local sample-only submit path from the active helper so it cannot be mistaken for the real production path.
- Validation:
  - Complete: A typed frontend check passes.
  - Pending: Browser submits reach `/api/demo/search` and `/api/demo/diagnose`.
  - Complete: The sample-data warning about local-only backend wiring no longer appears in live mode.
- Review:
  - The adapter registers placeholder product records for live products that were not present in the original demo catalog, so live product cards no longer disappear because of unknown ids.
  - Backend warnings are preserved and expanded with source and trace provenance when needed.
  - Errors are converted into visible low-confidence or empty-result demo responses instead of leaving the UI stuck in loading state.
  - Browser-level network verification is still pending and is included in final readiness validation.

### Phase 2: Confirm Endpoint Naming And Configuration

- Status: Complete
- Outcome: The app consistently targets the intended retail agent serving endpoint.
- Checklist:
  - Complete: Choose `agents_retail_assistant-retail-retail_agent_v3` as the canonical deployed serving endpoint.
  - Complete: Align the backend default, sample environment file, bundle variable, deployment docs, and demo script defaults to the same endpoint name.
  - Complete: Keep the endpoint configurable through environment or bundle variables.
  - Complete: Verify that sample mode and live mode are controlled only by explicit configuration.
  - Complete: Confirm fallback is disabled by default unless a demo environment intentionally enables it.
- Validation:
  - Complete: The Databricks serving endpoint list shows `agents_retail_assistant-retail-retail_agent_v3` is READY.
  - Complete: Local configuration defaults now report the expected endpoint.
  - Complete: The stale endpoint name appears only as a CLI command prefix, historical naming, or non-demo artifact text.
- Review:
  - The serving endpoint name is now consistent across the retail agent default config, demo-client backend default, demo-client environment sample, bundle variable, deploy helper default, and demo-client README.
  - `retail-graph-concierge-*` remains in command names and entry points because renaming those would be a broader CLI migration, not an endpoint configuration fix.
  - The endpoint remains overrideable through `RETAIL_AGENT_ENDPOINT_NAME`, `AGENTIC_COMMERCE_RETAIL_AGENT_ENDPOINT_NAME`, and bundle variables.

### Phase 3: Validate Live Backend Invocation

- Status: Complete
- Outcome: The demo-client backend can call the live retail agent and return frontend-safe responses.
- Checklist:
  - Complete: Run one live agentic search request through the backend route.
  - Complete: Run one live issue diagnosis request through the backend route.
  - Complete: Confirm session id and user id are passed through to the retail agent.
  - Complete: Confirm upstream request ids and latency are captured when Databricks returns them.
  - Complete: Confirm safe structured errors for authentication failure, permission failure, timeout, malformed response, and endpoint unavailable cases.
  - Complete: Confirm sample fallback is used only when explicitly enabled.
- Validation:
  - Complete: Live backend search returned `source_type=live`, `trace_source=live`, a Databricks request id, 8 tool timeline rows, 10 product picks, 5 knowledge chunks, and no warnings.
  - Complete: Live backend diagnosis returned `source_type=live`, `trace_source=live`, a Databricks request id, 4 tool timeline rows, 10 knowledge chunks, and no warnings.
  - Complete: Unit tests cover serving payload shape, session and user id pass-through, socket timeout mapping, safe upstream status mapping, sample responses, and adapter degradation when trace metadata is missing.
  - Complete: A log-shape test verifies request id, mode, endpoint name, source type, latency, Databricks request id, and fallback reason are emitted.
  - Complete: `uv run python -m unittest discover tests` passes in `demo-client`.
  - Complete: `apx dev check` passes.
  - Complete: Error responses match the documented frontend error shape through `DemoError`.
- Review:
  - The backend now derives a session-scoped user id when the browser does not provide one, so the agent receives both session and user context without introducing cross-demo identity leakage.
  - Live route validation confirms the backend calls the canonical Databricks Model Serving endpoint and normalizes both search and diagnosis responses into frontend-safe contracts.
  - Fallback remains disabled by default and is only used when explicitly configured.
  - The live search prompt revealed catalog/domain mismatch for computer peripherals, but the backend path, trace capture, and product normalization are working. Prompt and demo data fit are handled in Phase 5.

### Phase 4: Make The Agent Trace Fully Useful

- Status: Complete
- Outcome: The intelligence panels use real tool calls and real tool outputs when the agent calls tools.
- Checklist:
  - Complete: Verify the deployed retail agent version returns `custom_outputs.demo_trace`.
  - Complete: Confirm product search tool outputs become product cards.
  - Complete: Confirm related product tool outputs become the frequently paired or graph traversal lane.
  - Complete: Confirm GraphRAG knowledge tool outputs become chunks, sources, and graph-hop candidates.
  - Complete: Confirm issue diagnosis tool outputs become diagnosis path, actions, alternatives, and citations.
  - Complete: Add normalization for personalized recommendation tool output so recommendation results can become product cards.
  - Complete: Add clear warnings for non-JSON tool outputs, malformed tool outputs, or no tool calls.
  - Complete: Keep the normal assistant prose unchanged for existing agent consumers.
- Validation:
  - Complete: A live search prompt produced trace source `live`, 8 tool timeline rows, 10 product picks, 5 knowledge chunks, and no warnings.
  - Complete: A live diagnosis prompt produced trace source `live`, 4 tool timeline rows, 10 knowledge chunks, and no warnings.
  - Complete: A live preference-write prompt called `track_preference` and returned structured memory writes.
  - Complete: A live returning-user recommendation prompt called `get_user_profile` and `recommend_for_user`, proving the deployed endpoint uses real profile and recommendation tools.
  - Complete: Local trace extraction tests prove `recommend_for_user` output now becomes product results and profile chips.
  - Complete: Local trace extraction tests cover non-JSON tool output and no-tool trace warnings.
  - Complete: The retail agent endpoint was refreshed and endpoint smoke tests passed against the updated active route.
- Review:
  - Product search, GraphRAG, diagnosis, memory write, profile read, and recommendation tool calls are real, not mocked.
  - The demo trace is real LangGraph tool-call metadata from `custom_outputs.demo_trace`.
  - The local source now normalizes recommendation tool output into the same product-card path as catalog search.
  - The deployed serving endpoint now routes traffic to the refreshed canonical `retail_agent_v3` model.

### Phase 5: Improve Tool Selection For Demo Prompts

- Status: Complete
- Outcome: Representative demo prompts reliably exercise the real tools the UI is meant to showcase.
- Checklist:
  - Complete: Review the demo-mode prompt hints for search and diagnosis.
  - Complete: Add small prompt guidance if the agent skips the expected tools for common demo prompts.
  - Complete: Keep tool choice agentic, but make the desired demo behavior reliable enough for stakeholder walkthroughs.
  - Complete: Add representative checks for search, diagnosis, profile read, preference write, recommendation, and trace capture.
  - Complete: Record known prompts that still return prose-only answers.
- Validation:
  - Complete: The primary search prompt now asks for waterproof trail running shoes under $150, matching the live outdoor and fitness catalog.
  - Complete: The primary support prompt now asks about running shoes that feel flat after 300 miles, matching the live GraphRAG support corpus.
  - Complete: Live search called `get_user_profile`, `search_products`, and `track_preference`, returned 14 product cards, and produced trace source `live`.
  - Complete: Live diagnosis called `knowledge_search`, returned 5 knowledge chunks, 5 cited sources, 8 recommended actions, and produced trace source `live`.
  - Complete: A returning-user recommendation prompt called `get_user_profile` and `recommend_for_user`.
  - Complete: Local tests and `apx dev check` pass after the prompt and sample-data changes.
  - Notes: No revised primary prompt returned prose-only output during validation. The recommendation prompt used the real recommendation tool, but structured recommendation cards still require the endpoint refresh recorded in Phase 6.
- Review:
  - The old electronics-oriented demo prompts were removed from the active frontend and backend sample paths.
  - The sample fallback data now mirrors the live catalog domain so fallback mode does not tell a different product story from live mode.
  - The prompt hints now include outdoor and fitness examples, which should take effect after the retail agent endpoint is refreshed.

### Phase 6: Validate Deployed App Permissions

- Status: In progress
- Outcome: The Databricks App can query the serving endpoint from its deployed runtime.
- Checklist:
  - Complete: Refresh the retail agent serving endpoint so the active model version includes the latest trace normalization.
  - Pending: Re-run the live recommendation prompt and confirm structured recommendation cards are returned from the deployed app path.
  - Confirm the app resource grants query permission to the serving endpoint.
  - Deploy the app with live mode enabled.
  - Submit one search request from the deployed app.
  - Submit one diagnosis request from the deployed app.
  - Check deployed app logs for endpoint name, request id, source type, latency, and fallback behavior.
  - Confirm no Databricks credentials, Neo4j credentials, authorization headers, or raw secrets appear in user-visible responses or logs.
- Validation:
  - Pending: Deployed search returns a live response or a clearly marked fallback if fallback is intentionally enabled.
  - Pending: Deployed diagnosis returns a live response or a clearly marked fallback if fallback is intentionally enabled.
  - Pending: The app works without relying on a local Databricks CLI profile.
  - Complete: The serving endpoint is READY with no pending config and routes 100% traffic to `retail_assistant-retail-retail_agent_v3_10`.
  - Pending: `retail-graph-concierge-demo` and `retail-graph-concierge-check-knowledge` need to be rerun against model version 10.
  - Notes: Databricks App deployment and app-runtime permission validation remain pending.

### Phase 7: Final Demo Readiness

- Status: Pending
- Outcome: The demo is repeatable, honest about provenance, and ready for stakeholder walkthroughs.
- Checklist:
  - Run backend unit tests.
  - Run Python compile checks.
  - Run frontend and backend type checks.
  - Build the app.
  - Verify desktop and mobile layouts in a browser.
  - Verify live, sample, fallback, inferred, and unavailable states render distinctly.
  - Update the demo script with exact prompts, expected panels, fallback notes, and reset steps.
  - Document any remaining limitations in this file.
- Validation:
  - The visible demo no longer claims sample data is the active path in live mode.
  - The presenter can reset and rerun both tabs without confusing stale frontend state.
  - The completion criteria below are all satisfied or explicitly marked blocked.

## Completion Criteria

- Status: Pending
- The React client submits through the backend API routes for both demo tabs.
- The backend invokes the configured Databricks Model Serving endpoint in live mode.
- The frontend never needs Databricks credentials or raw Model Serving URLs.
- Search can render live product or recommendation results when the agent returns them.
- Issue diagnosis can render live GraphRAG chunks, citations, actions, and diagnosis details when the agent returns them.
- The intelligence panel uses real LangGraph tool-call trace data when available.
- Sample data is used only in sample mode or explicitly enabled fallback mode.
- Fallback and inferred data are visibly labeled.
- Endpoint naming is consistent across configuration, deployment, and docs.
- Deployed app permission to query the serving endpoint is validated.
- Tests, checks, build, and browser verification have passed.

## Deferred Work

- Server-side memory reset for a demo user or demo session.
- Full operator console or behind-the-glass trace replay.
- Bundle builder and comparison pages beyond the two current tabs.
- Persistent session replay, saved carts, feedback capture, or Lakebase-backed history.
- Exact token accounting and exact per-tool timing.

## Historical Documents

- `EXPAND.md` is historical background for the retail agent GraphRAG and memory expansion.
- `docs/agentic-commerce-demo.md` is historical background for demo framing and wireframes.
- `docs/demo-client-backend-gap.md` is superseded by this plan.
- `docs/demo-client-plan.md` is superseded by this plan.
