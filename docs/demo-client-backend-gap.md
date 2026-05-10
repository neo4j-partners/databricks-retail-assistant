# Demo Client Backend Gap Plan

## Goal

Update the backend plan for `demo-client` so the apx React client can implement the two-tab agentic commerce demo:

- Agentic search with ranked product answers, profile updates, related products, and an intelligence surge panel.
- Issue diagnosis with symptom-to-cause-to-solution reasoning, recommended actions, alternatives, and cited sources.

This plan covers the `demo-client` FastAPI backend and the scoped upstream `retail_agent` changes needed to make most demo data live while keeping the browser isolated from Databricks Model Serving internals.

## Recommended Direction

- Status: Accepted
- Keep the first version simple enough for a basic demo while making most demo data live.
- The `demo-client` backend owns the frontend contract, session generation, fallback behavior, and response normalization.
- The upstream `retail_agent` should be updated now, but only in a scoped way: preserve the normal ChatAgent assistant prose response and add demo-specific structured metadata in `ChatAgentResponse.custom_outputs`.
- The first upstream target is `custom_outputs.demo_trace`, populated from real LangGraph tool calls and tool results that already exist inside the agent execution.
- Do not build backend streaming or polling for live progress in version one. The backend should return final timing metadata; the frontend can render deterministic progress animation while a request is pending.
- Do not block the demo on exact token accounting or complete per-tool timing. Add those later if they are easy to extract reliably.
- Use curated sample data only for local development, exact preset demos, and explicitly enabled fallback. Most non-preset demo flows should call the live endpoint.

## Implementation Progress

- Status: In Progress
- `demo-client` backend contract, routes, config, sample data, live adapter, serving invocation wrapper, fallback behavior, session generation, logging, and no-Databricks adapter tests have been implemented.
- New backend routes:
  - `POST /api/demo/search` with operation id `runAgenticSearch`.
  - `POST /api/demo/diagnose` with operation id `runIssueDiagnosis`.
- New backend config fields use the existing app env prefix:
  - `AGENTIC_COMMERCE_RETAIL_AGENT_ENDPOINT_NAME`
  - `AGENTIC_COMMERCE_RETAIL_AGENT_TIMEOUT_SECONDS`
  - `AGENTIC_COMMERCE_DEMO_DATA_MODE`
  - `AGENTIC_COMMERCE_DEMO_ALLOW_SAMPLE_FALLBACK`
  - `AGENTIC_COMMERCE_DEMO_INCLUDE_RAW_ENDPOINT_METADATA`
- The backend now prefers upstream `custom_outputs.demo_trace`, degrades prose-only live responses safely, and uses sample data only in sample mode or explicitly enabled fallback.
- QA cleanup completed: route-specific demo modes are deterministic, upstream auth failures are wrapped, upstream HTTP statuses are mapped to safe frontend statuses, and error response bodies now match the documented `DemoError` schema.
- Verification completed locally:
  - `uv run python -m unittest discover -s tests`
  - `uv run python -m compileall src/agentic_commerce/backend tests`
  - `uv run apx dev check`
  - OpenAPI smoke check confirmed `runAgenticSearch` and `runIssueDiagnosis`.
- Still pending:
  - Upstream `retail_agent` implementation of `custom_outputs.demo_trace`.
  - Live endpoint validation with the updated upstream model.
  - Deployed Databricks App service-principal permission validation.
  - Final reset semantics decision.

## Current State

- Status: Complete
- The `retail_agent` Model Serving endpoint exists and is ready.
- The endpoint name is `retail-graph-concierge`.
- The endpoint serves Unity Catalog model `retail_assistant.retail.retail_graph_concierge`.
- Model version `5` currently receives all endpoint traffic.
- The endpoint has Neo4j secrets wired into its serving environment.
- A direct endpoint invocation returns ChatAgent-style JSON with assistant messages and Databricks request metadata.
- The live endpoint response is useful for answer text, but it does not currently return the structured fields the demo UI needs for product cards, graph hops, chunks, memory writes, source rows, latency, or token counts.
- The MLflow `ChatAgentResponse` type supports `custom_outputs`, which is the preferred path for returning structured demo metadata without breaking normal chat consumers.
- The existing `retail_agent` tools already return JSON for product search, related products, knowledge search, issue diagnosis, profile lookup, preference tracking, and reasoning trace operations.
- The `demo-client` backend now exposes version, current-user, agentic search, and issue diagnosis routes.
- The `demo-client` backend now has app config, Databricks dependency helpers, demo response models, endpoint invocation code, response normalization, and sample demo data handling.

## Client Needs

- Status: Pending
- The frontend needs stable backend routes for agentic search and issue diagnosis.
- The frontend needs typed response shapes so apx can generate a usable TypeScript client.
- The frontend needs consistent display data whether the source is live Model Serving output or sample demo data.
- The frontend needs a session identifier to support multi-turn memory and clean reset behavior.
- The frontend needs profile chips and memory deltas for the header and intelligence surge panel.
- The frontend needs enough timing information to show pending-state progress animation and final request metadata.
- The frontend needs graceful degraded output when the live endpoint returns prose only.
- The frontend must not call Databricks Model Serving directly from the browser.

## Backend Gaps

- Status: Mostly Implemented
- App configuration for the serving endpoint name, invocation timeout, sample data mode, fallback behavior, and diagnostics metadata has been added.
- Backend request and response models for both demo modes have been added.
- FastAPI routes for agentic search and issue diagnosis have been added.
- A Model Serving invocation wrapper has been added.
- A response adapter for ChatAgent `messages` and `custom_outputs.demo_trace` has been added.
- Curated backend-owned sample demo data has been added for the four design presets.
- A stable error model has been added.
- Request logging records request id, mode, session id, endpoint name, latency, source type, Databricks request id, and fallback reason without prompt text or secrets.
- Missing validation that the Databricks App service principal can query the serving endpoint.
- Missing upstream `retail_agent` support for structured demo metadata in `custom_outputs.demo_trace`.

## Phase Checklist

### Phase 1: Lock the Backend Contract

- Status: Implemented
- Outcome: The backend contract is explicit enough for frontend implementation and OpenAPI generation.
- Checklist:
  - Define one request shape for agentic search.
  - Define one request shape for issue diagnosis.
  - Include prompt text, optional session id, optional user id, optional demo preset id, and optional demo mode in each request.
  - Require the backend to generate a session id when the request does not include one.
  - Return the effective session id in every successful response.
  - Define one shared response envelope with mode, answer text, source type, trace source, request id, warnings, and timing metadata.
  - Define search-specific response fields for summary, product picks, related products, profile chips, memory writes, tool timeline, graph hops, and knowledge chunks.
  - Define diagnosis-specific response fields for summary, confidence, path, recommended actions, compatible alternatives, cited sources, and tool timeline.
  - Define a stable error response that supports user-facing message, technical detail, retryability, and fallback availability.
  - Give every route a stable operation identifier for generated client hooks.
- Implementation details:
  - Keep the contract close to what the UI needs rather than exposing raw Model Serving JSON.
  - Treat live endpoint prose as one possible input, not as the frontend contract.
  - Use a top-level `source_type` with values like `live`, `sample`, and `fallback`.
  - Use a top-level `trace_source` with values like `live`, `sample`, `inferred`, and `unavailable`.
  - Avoid per-field provenance in version one unless a section mixes live and non-live data in a way the UI must display.
  - Allow fields to be absent, but make absence explicit through warnings or empty lists.
  - If fallback to sample data is enabled and succeeds, return HTTP 200 with `source_type: fallback` and a visible warning.
  - If fallback is disabled or unavailable, return a structured non-2xx error.
  - Treat live progress as a frontend pending-state animation in version one; the backend returns final timing only.
- Validation:
  - OpenAPI describes both demo routes with stable request and response models.

### Phase 2: Add Configuration and Environment Wiring

- Status: Implemented, Deployment Validation Pending
- Outcome: The backend can be configured locally and inside Databricks Apps without hardcoded runtime values.
- Checklist:
  - Add a config field for the retail agent serving endpoint name.
  - Default the endpoint name to `retail-graph-concierge`.
  - Add a config field for request timeout.
  - Add a config field for sample data mode.
  - Add a config field for whether fallback to sample data is allowed.
  - Add a config field for whether raw endpoint metadata may be included for development diagnostics.
  - Document the corresponding environment variable names for local and deployed app usage.
  - Avoid storing Databricks tokens, Neo4j secrets, or endpoint URLs in source code.
- Implementation details:
  - Use the existing app config pattern in `demo-client`.
  - Use Databricks App resource or environment-backed configuration for deployed values.
  - Keep the endpoint name configurable even though the current endpoint is known.
- Validation:
  - Local config can run with sample data only.
  - Local config can run against the live endpoint when Databricks auth is available.
  - Deployed config can resolve the endpoint name without code changes.
  - Deployed demo config can explicitly enable or disable live-to-sample fallback.

### Phase 3: Implement the Model Serving Invocation Layer

- Status: Implemented, Live Validation Pending
- Outcome: The `demo-client` backend can call the live `retail_agent` endpoint safely and consistently.
- Checklist:
  - Add one backend helper responsible for invoking Model Serving.
  - Send ChatAgent-compatible messages to the endpoint.
  - Pass session id and user id in the request so `retail_agent` memory can scope interactions.
  - Pass `demo_mode` in `custom_inputs` so `retail_agent` can bias tool selection for `agentic_search` or `issue_diagnosis`.
  - Prefer authenticated backend-side Databricks access through the existing app-level client or config.
  - Avoid browser-side Databricks credentials.
  - Avoid relying on the Databricks CLI query behavior for application runtime.
  - Preserve Databricks request id from responses when available.
  - Measure backend-side latency for every endpoint invocation.
  - Handle endpoint timeout, endpoint not found, non-ready endpoint, permission failure, malformed response, and upstream server error.
- Implementation details:
  - The repo's existing `retail_agent` test client uses direct REST because the SDK query path may not deserialize ChatAgent responses cleanly.
  - The `demo-client` backend should follow that practical pattern, but use app authentication instead of local CLI credentials when deployed.
  - The invocation layer should return raw response data only to the adapter layer, not directly to the frontend.
  - Preserve both `messages` and `custom_outputs` from the ChatAgent response.
- Validation:
  - A backend route can submit a prompt and receive assistant message text from the live endpoint.
  - The backend receives `custom_outputs.demo_trace` when the upstream endpoint returns it.
  - The backend records the Databricks request id and latency.

### Phase 4: Build the Live Response Adapter

- Status: Implemented, Upstream Trace Validation Pending
- Outcome: ChatAgent responses with live `custom_outputs.demo_trace` render as structured demo responses, while prose-only responses still degrade cleanly.
- Checklist:
  - Extract the final assistant message text from ChatAgent responses.
  - Preserve Databricks request metadata.
  - Prefer structured data from `custom_outputs.demo_trace` over prose parsing.
  - Map live `product_results` to ranked product cards.
  - Map live `related_products` to related product surfaces.
  - Map live `knowledge_chunks` to cited source rows and intelligence surge chunks.
  - Map live `diagnosis` fields to symptom, cause, solution, action, and alternative sections.
  - Map live `memory_writes` and profile results to profile chips and memory deltas.
  - Extract simple ranked product rows from markdown tables only when structured data is absent.
  - Extract product names, brands, prices, and availability from prose only as a best-effort fallback.
  - Extract short highlights into rationale text when possible and clearly mark them as inferred.
  - Create monogram product placeholders when no image or product id is available.
  - Detect support-style answers and map them to diagnosis summary text when possible.
  - Do not pretend inferred data is authoritative.
  - Add warnings when product cards, sources, trace rows, or memory writes are inferred or unavailable.
  - Return empty trace sections when live data does not include trace details.
- Implementation details:
  - Use conservative parsing. A clean prose answer is better than unreliable fake structure.
  - The adapter should never fail the whole request just because a product card cannot be inferred.
  - The adapter should keep raw answer text available so the UI can always show a truthful response.
- Validation:
  - A live search response with `custom_outputs.demo_trace.product_results` renders as product cards without markdown parsing.
  - A live support response with `custom_outputs.demo_trace.knowledge_chunks` and `diagnosis` renders as cited diagnosis output.
  - The known running-shoes endpoint response renders as answer text and best-effort product cards.
  - A prose-only response renders without frontend errors.

### Phase 5: Add Sample Demo Data Support

- Status: Implemented
- Outcome: The backend can supply polished demo-shaped responses when live endpoint output is not structured enough.
- Checklist:
  - Move the relevant design sample responses into backend-owned demo data.
  - Include the two search samples from the design: MacBook coding mouse and frequent traveler headphones.
  - Include the two support samples from the design: headphones disconnect during calls and printer offline.
  - Support preset ids so the frontend can request exact demo scenarios.
  - If `demo_preset_id` is present in sample mode, return the exact preset and ignore prompt content for response selection.
  - If `demo_preset_id` is present in live mode, use it only as fallback selection metadata unless live behavior explicitly supports it later.
  - If live fallback occurs and `demo_preset_id` is available, return the matching preset.
  - Allow sample data mode for local development.
  - Allow optional fallback to sample data when the live endpoint is unavailable.
  - Return a clear warning when sample data is used.
  - Keep sample data separate from live endpoint adapter logic.
- Implementation details:
  - Sample demo data is not test data in the narrow unit-test sense. It is curated presentation data used to preserve the designed user experience.
  - Sample demo data should be easy to remove or disable in production.
  - The deployed app should only fall back to sample data if that behavior is explicitly enabled.
- Validation:
  - All four design presets return full demo-shaped responses without calling Model Serving.
  - Fallback behavior is visible in logs and optionally visible in the UI.

### Phase 6: Implement Trace Strategy

- Status: In Progress
- Outcome: The intelligence surge panel uses real live trace data when available and clearly identifies sample, inferred, or unavailable sections otherwise.
- Checklist:
  - Use live trace rows from upstream `custom_outputs.demo_trace` as the primary source.
  - Use sample trace rows for curated presets and explicitly enabled fallback.
  - Use inferred trace rows only for conservative prose-derived fallback.
  - Mark missing live trace data as unavailable rather than fabricating details.
  - Update `retail_agent` so the Model Serving response includes structured tool timeline, graph hops, retrieved chunks, product results, diagnosis results, profile reads, and memory writes when those are present in real tool output.
  - Use `ChatAgentResponse.custom_outputs` for structured metadata.
  - Keep the assistant prose in `messages` unchanged so notebooks, scripts, and existing checks continue to work.
  - Avoid exposing secrets, internal headers, Neo4j credentials, or raw tool inputs that could leak sensitive data.
- Implementation details:
  - The current `retail_agent` serving adapter returns only assistant messages from the LangGraph result.
  - That filtering likely drops the intermediate information the UI wants to show.
  - A proper live trace requires upstream changes in `retail_agent`, not just `demo-client`.
  - Version one should use a hybrid strategy: live first, sample for presets/fallback, inferred only when conservative, unavailable when not present.
- Validation:
  - The backend response clearly identifies whether trace rows are live, inferred, unavailable, or sample-backed.
  - Live endpoint responses contain `custom_outputs.demo_trace` for representative search and support prompts.

### Phase 6A: Add Scoped Upstream `retail_agent` Demo Metadata

- Status: In Progress by upstream agent
- Outcome: The live endpoint returns enough structured metadata for most of the demo without changing the normal assistant response.
- Checklist:
  - Add a small trace extraction helper in `retail_agent` that inspects LangGraph output messages after `ainvoke`.
  - Capture AI tool calls into a live `tool_timeline`.
  - Capture ToolMessage names, ids, and JSON content when available.
  - Normalize `search_products` output into `product_results`.
  - Normalize `get_related_products` output into `related_products`.
  - Normalize `knowledge_search` and `hybrid_knowledge_search` output into `knowledge_chunks`, source rows, symptoms, solutions, features, and graph-hop candidates.
  - Normalize `diagnose_product_issue` output into diagnosis details.
  - Normalize `get_user_profile` output into profile chips.
  - Normalize `track_preference` output into memory writes.
  - Include `trace_source: live` when at least one real tool output was captured.
  - Include warnings for tool outputs that are non-JSON, malformed, or intentionally omitted.
  - Return the normalized payload under `ChatAgentResponse.custom_outputs.demo_trace`.
  - Keep exact per-tool timing and token accounting out of scope unless available from existing metadata without intrusive changes.
  - Add `demo_mode` handling from `custom_inputs` to bias prompts and tool selection for `agentic_search` and `issue_diagnosis`.
- Implementation details:
  - This is a serving adapter and normalization change, not a rewrite of the agent.
  - Do not change the public behavior of existing tools unless a small structured-field improvement is needed.
  - Avoid adding a second endpoint for traces in version one.
  - The first implementation can derive graph hops from returned chunk entities and related product fields rather than tracing every Cypher edge.
  - If a tool returns plain text, include it in the tool timeline but do not force it into product or diagnosis structures.
- Validation:
  - Existing endpoint checks that read assistant prose still pass.
  - A live agentic search prompt returns assistant prose plus `custom_outputs.demo_trace.product_results`.
  - A live issue diagnosis prompt returns assistant prose plus `custom_outputs.demo_trace.knowledge_chunks` or `diagnosis`.
  - A prompt that produces no tool calls still returns valid assistant prose and `trace_source: unavailable` or no demo trace.

### Phase 7: Add Demo Routes

- Status: Implemented
- Outcome: The frontend has exactly the backend routes it needs.
- Checklist:
  - Add an agentic search route under the existing API prefix.
  - Add an issue diagnosis route under the existing API prefix.
  - Use typed request models and typed response models.
  - Use stable operation identifiers.
  - Use the configured data mode to choose live endpoint, sample data, or fallback behavior.
  - Return frontend-ready response objects.
  - Keep existing version and current-user routes working.
- Implementation details:
  - Keep route handlers thin.
  - Put endpoint invocation, response adaptation, and sample data selection behind backend helper boundaries.
  - Do not make frontend components understand Model Serving response internals.
- Validation:
  - apx OpenAPI generation sees both routes.
  - The generated frontend client can call both routes.

### Phase 8: Add Session and Reset Support

- Status: Partially Implemented
- Outcome: The backend supports clean demo sessions and memory scoping.
- Checklist:
  - Accept an optional session id on each request.
  - Generate a session id in the backend when the request does not include one.
  - Return the effective session id in each successful response.
  - Accept optional user id when personalization is enabled.
  - Pass session id and user id through to `retail_agent` for live calls.
  - Define what reset means for the backend.
  - If reset is browser-only, document that server-side memory may persist.
  - If reset should clear server-side memory, identify or add a safe upstream memory-clear capability.
  - Avoid destructive memory clearing unless it is scoped to the demo session or demo user.
- Implementation details:
  - Browser reset is enough for visual state.
  - Server-side memory reset is a separate capability and should be treated as higher risk.
  - The first release can use unique session ids to avoid stale session state without deleting memory.
- Validation:
  - A presenter can run the same demo repeatedly without stale frontend state.
  - Live calls use unique session ids unless a deliberate multi-turn session is being shown.

### Phase 9: Add Observability and Safe Error Handling

- Status: Implemented, Failure Injection Validation Pending
- Outcome: Backend failures are easy to diagnose and safe to show in the UI.
- Checklist:
  - Log request mode, endpoint name, session id, source type, latency, request id, and fallback reason.
  - Do not log prompt text by default if that could contain user-sensitive information.
  - Do not log Databricks tokens, Neo4j credentials, or authorization headers.
  - Convert upstream failures into structured frontend errors.
  - Mark retryable errors clearly.
  - Include enough detail for development logs without showing raw stack traces to users.
  - Add health or diagnostics information only if it is useful to the frontend or deployment checks.
- Implementation details:
  - The UI needs enough information to show "live endpoint unavailable, using sample demo data" or "try again."
  - Logs need enough information to correlate a UI failure with a Databricks request id.
- Validation:
  - Simulated timeout and permission failures produce useful frontend-safe errors.
  - Logs include correlation details without secrets.

### Phase 10: Validate App Permissions and Deployment

- Status: Pending
- Outcome: The deployed Databricks App can call the deployed retail agent endpoint.
- Checklist:
  - Confirm the Databricks App service principal has permission to query `retail-graph-concierge`.
  - Confirm the app can resolve the endpoint configuration after deployment.
  - Confirm deployed backend auth works without local CLI profile assumptions.
  - Confirm the endpoint can access Neo4j and its embedding dependencies from serving.
  - Confirm the app logs show endpoint request ids and fallback reasons.
  - Decide whether the existing Lakebase resource should remain in the app bundle.
- Implementation details:
  - Local CLI auth success does not prove deployed app auth success.
  - Deployed verification must test from inside the app runtime or with equivalent app credentials.
  - Lakebase is not required for the first backend contract unless saved sessions, replay, feedback, or cart persistence becomes scope.
- Validation:
  - The deployed app backend successfully returns a live search response.
  - The deployed app backend successfully returns a live support response or documented fallback response.

## Future Upstream `retail_agent` Improvements

- Status: Pending
- Add exact per-tool timing when reliable timing metadata is available from LangGraph or wrapper instrumentation.
- Add token metadata when reliable usage data is available from the model or serving response.
- Add richer graph-hop records if the demo needs edge-level path visualization rather than chunk-derived graph context.
- Add a separate trace retrieval path only if `custom_outputs.demo_trace` proves insufficient.
- Add stricter tool-selection tests for representative search and support prompts.

## Completion Criteria

- Status: In Progress
- Complete: `demo-client` has backend routes for agentic search and issue diagnosis.
- Complete: The routes are represented in OpenAPI with stable operation identifiers.
- Implemented, pending live validation: The backend can call `retail-graph-concierge`.
- The live endpoint can return assistant prose plus `custom_outputs.demo_trace` for representative demo prompts.
- Complete: The backend can return sample demo data without calling Model Serving.
- Complete, pending live validation: The backend can adapt live ChatAgent `custom_outputs.demo_trace` into frontend-safe response objects.
- Complete: The backend can degrade prose-only live responses without frontend errors.
- Complete: The backend makes trace provenance explicit: live, inferred, unavailable, or sample-backed.
- Complete: The frontend never needs Databricks credentials or raw Model Serving URLs.
- Deployed app auth to the serving endpoint has been validated.
- Complete: Logs include request ids, latency, source type, and fallback reason without secrets.

## Open Questions

- Status: Pending
- Which deployed demo environments should explicitly enable live-to-sample fallback?
- Should reset remain browser-only for version one, or should it clear server-side memory for a scoped demo user?
- Should the existing Lakebase resource stay in the demo-client bundle if no backend persistence is required?
