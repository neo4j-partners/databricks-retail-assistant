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

- Status: Pending
- Outcome: The demo-client backend can call the live retail agent and return frontend-safe responses.
- Checklist:
  - Run one live agentic search request through the backend route.
  - Run one live issue diagnosis request through the backend route.
  - Confirm session id and user id are passed through to the retail agent.
  - Confirm upstream request ids and latency are captured when Databricks returns them.
  - Confirm safe structured errors for authentication failure, permission failure, timeout, malformed response, and endpoint unavailable cases.
  - Confirm sample fallback is used only when explicitly enabled.
- Validation:
  - Live backend responses return answer text without frontend errors.
  - Logs include request id, mode, endpoint name, source type, latency, Databricks request id when available, and fallback reason when applicable.
  - Error responses match the documented frontend error shape.

### Phase 4: Make The Agent Trace Fully Useful

- Status: Pending
- Outcome: The intelligence panels use real tool calls and real tool outputs when the agent calls tools.
- Checklist:
  - Verify the deployed retail agent version returns `custom_outputs.demo_trace`.
  - Confirm product search tool outputs become product cards.
  - Confirm related product tool outputs become the frequently paired or graph traversal lane.
  - Confirm GraphRAG knowledge tool outputs become chunks, sources, and graph-hop candidates.
  - Confirm issue diagnosis tool outputs become diagnosis path, actions, alternatives, and citations.
  - Add normalization for personalized recommendation tool output so recommendation results can become product cards.
  - Add clear warnings for non-JSON tool outputs, malformed tool outputs, or no tool calls.
  - Keep the normal assistant prose unchanged for existing agent consumers.
- Validation:
  - A live search prompt produces trace source `live` when real tool output is captured.
  - A live diagnosis prompt produces live chunks, sources, or diagnosis details when the agent uses GraphRAG tools.
  - A recommendation prompt with stored preferences produces live recommendation cards or an explicit unavailable warning.

### Phase 5: Improve Tool Selection For Demo Prompts

- Status: Pending
- Outcome: Representative demo prompts reliably exercise the real tools the UI is meant to showcase.
- Checklist:
  - Review the demo-mode prompt hints for search and diagnosis.
  - Add small prompt guidance if the agent skips the expected tools for common demo prompts.
  - Keep tool choice agentic, but make the desired demo behavior reliable enough for stakeholder walkthroughs.
  - Add representative checks for search, diagnosis, profile read, preference write, recommendation, and trace capture.
  - Record known prompts that still return prose-only answers.
- Validation:
  - The primary search prompt calls product or recommendation tools.
  - The primary support prompt calls GraphRAG or diagnosis tools.
  - A returning-user recommendation prompt reads preferences or reports that no user profile exists.

### Phase 6: Validate Deployed App Permissions

- Status: Pending
- Outcome: The Databricks App can query the serving endpoint from its deployed runtime.
- Checklist:
  - Confirm the app resource grants query permission to the serving endpoint.
  - Deploy the app with live mode enabled.
  - Submit one search request from the deployed app.
  - Submit one diagnosis request from the deployed app.
  - Check deployed app logs for endpoint name, request id, source type, latency, and fallback behavior.
  - Confirm no Databricks credentials, Neo4j credentials, authorization headers, or raw secrets appear in user-visible responses or logs.
- Validation:
  - Deployed search returns a live response or a clearly marked fallback if fallback is intentionally enabled.
  - Deployed diagnosis returns a live response or a clearly marked fallback if fallback is intentionally enabled.
  - The app works without relying on a local Databricks CLI profile.

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
