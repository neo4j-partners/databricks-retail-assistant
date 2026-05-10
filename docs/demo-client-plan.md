# Demo Client Implementation Plan

## Goal

Build the exported Claude Design `index.html` experience in `demo-client` as an apx Databricks App.

The target is the `retail/agent` two-page demo from the design bundle:

- Agentic search: a shopper asks a natural-language catalog question and receives ranked product picks, rationale, signals, frequently paired items, profile updates, and a live intelligence surge panel.
- Issue diagnosis: a shopper describes a product problem and receives a symptom-to-cause-to-solution path, recommended actions, compatible alternatives, and cited sources.

The implementation should adapt the relevant visual and interaction behavior from the design into the existing apx style rather than copying the prototype pixel for pixel. Keep the clean two-tab structure, live trace story, and compact product/support surfaces, but use the real project stack: FastAPI backend, React frontend, apx layout conventions, shadcn-style components where appropriate, OpenAPI-generated client, Databricks SDK authentication, Databricks Model Serving, apx development workflow, and Databricks App deployment.

## Design Source

- Status: Complete
- The design handoff bundle was fetched from the Anthropic design URL.
- The bundle README says to read the chat transcript first, then read `project/index.html` in full and follow its imports.
- `project/index.html` loads `styles.css`, `data.js`, and `app.jsx`; those files define the primary design.
- The chat transcript says the user wanted a clean, simple, high-quality demo with a couple of pages.
- The final design landed on two tabs in one app: `01 Agentic search` and `02 Issue diagnosis`.
- The design uses Helvetica Neue for general UI and JetBrains Mono for instrumentation, trace, and technical labels.
- The design uses warm paper neutrals, near-black ink, one cool blue accent, and one green live indicator.
- The design uses typographic monogram product placeholders rather than fake product photos.
- The most important interaction is an animated reveal that makes tool calls, graph hops, knowledge chunks, source citations, and memory writes feel live.

## Client Progress

- Status: In progress
- Complete: The apx starter landing page has been replaced with the `retail/agent` demo shell.
- Complete: The client now has two tabs: Agentic search and Issue diagnosis.
- Complete: The client uses local sample demo data for the four design scenarios while backend routes are being built.
- Complete: The client includes reusable product cards, compact related-product cards, intelligence surge panel, trace rows, graph hop rows, knowledge chunk rows, memory write rows, diagnosis path, source citation rows, empty states, loading states, warning states, local session id, and reset behavior.
- Complete: The UI blends the design direction into apx/shadcn-style components rather than copying the prototype pixel for pixel.
- Complete: `apx dev check` passes.
- Complete: `apx build` passes.
- Pending: The client still needs to swap the local sample data seam to generated apx API calls once backend demo routes are implemented.
- Pending: Browser verification across desktop and mobile viewports has not been run yet.
- Pending: Live Model Serving response rendering still depends on backend response adaptation.

## Assumptions

- Status: Pending
- The active implementation path is `demo-client/src/agentic_commerce`.
- The similarly named `demo-client/src/agentic_commerece` tree appears stale or accidental and should not be expanded unless cleanup is approved.
- The placeholder apx landing page should be replaced by the actual demo experience.
- The app should open directly to the `retail/agent` shell, not to a marketing page.
- The UI should blend into apx styling instead of being a pixel-perfect clone of the exported prototype.
- The browser should call the demo client's FastAPI API, and the FastAPI backend should call the Databricks Model Serving endpoint.
- The deployed retail agent is a Databricks Model Serving ChatAgent endpoint.
- The serving endpoint name is `agents_retail_assistant-retail-retail_agent_v3`.
- The endpoint currently serves Unity Catalog model `retail_assistant.retail.retail_agent_v3` version 5 at 100 percent traffic.
- The endpoint is in `READY` state as of the review.
- Databricks SDK authentication should use the app's configured credentials through the existing dependency pattern.
- Endpoint names, resource identifiers, and demo toggles should come from Databricks App configuration or environment-backed settings, not hardcoded values.
- The first implementation should preserve the design's canned-demo behavior as sample demo data for local development, screenshots, and endpoint outages.
- Live Databricks responses should be normalized into the same display shape used by the design so the UI can render consistently.
- apx MCP tools should be used for apx checks, component discovery, OpenAPI refresh, and Databricks SDK documentation lookup when available.
- Databricks MCP tools should be used for endpoint inspection, app deployment, app logs, and workspace lifecycle when available.
- If an MCP server is unavailable during implementation, use the equivalent apx, Databricks CLI, or SDK workflow and record the fallback.

## Risks

- Status: Pending
- The current ChatAgent response returns `messages` and Databricks request metadata. It does not currently return the design's structured product picks, graph hops, chunks, sources, memory writes, latency, and token counts as separate response fields.
- Because the endpoint currently returns mostly prose, the backend adapter needs either best-effort extraction or sample demo data to preserve the designed product cards, trace panel, and source rail.
- The reviewed endpoint currently has scale-to-zero disabled, but the UI should still keep the design's streaming and loading language clear for slow endpoint calls.
- User-level personalization may require on-behalf-of auth scopes. Version one should work with app-level service principal auth unless user auth is confirmed.
- Product images may not be available. The design intentionally uses monogram placeholders, so missing images should not block implementation.
- The design is a prototype, not production React code. Match the visual output and user experience, but adapt the internal structure to apx, TanStack Router, generated API hooks, and local component conventions.
- Lakebase is already in the bundle, but the design does not require persistent database state. Do not add Lakebase tables unless replay, saved sessions, feedback, or server-side session reset becomes part of scope.

## Phase Checklist

### Phase 1: Confirm Design and Runtime Contracts

- Status: Pending
- Outcome: The team knows exactly which parts of the design are in scope and what the live endpoint can return.
- Checklist:
  - Treat the exported `index.html` design as the primary UI source.
  - Carry forward the two-tab scope: Agentic search and Issue diagnosis.
  - Carry forward the `retail/agent` header, profile chip, reset action, and footer.
  - Carry forward the animated live reveal behavior for demo answers.
  - Confirm that implementation should blend into the existing apx shell while keeping the design's two-tab structure and live trace story.
  - Verify whether the apx MCP server is available.
  - Verify whether Databricks MCP tools are available.
  - Use `agents_retail_assistant-retail-retail_agent_v3` as the serving endpoint name.
  - Confirm endpoint readiness before live integration work.
  - Capture the actual ChatAgent response shape: `messages` plus Databricks request metadata.
  - Document which design fields can come directly from the endpoint and which need fallback, sample data, or adapter logic.
- Validation:
  - A short response-contract note exists before implementation starts.
  - The design scope is locked to the two tabbed pages unless the user expands it.

### Phase 2: Define the Demo Response Contract

- Status: Pending
- Outcome: The frontend can render both live endpoint responses and canned design responses through one stable shape.
- Checklist:
  - Define a search response shape that supports query, summary, ranked picks, product metadata, rationale, signals, frequently paired products, profile writes, profile chips, tool timeline, graph hops, knowledge chunks, latency, and token count.
  - Define a support response shape that supports query, summary, confidence, diagnosis path, recommended actions, cited sources, compatible alternatives, tool timeline, latency, and token count.
  - Preserve the design's two sample search scenarios for local development.
  - Preserve the design's two sample support scenarios for local development.
  - Add a backend mode that can use sample demo data when the live endpoint is missing, disabled, slow, or unsuitable for visual demos.
  - Normalize live ChatAgent responses into the same search or support shape as far as the available data allows.
  - Include warnings when a displayed field is inferred, unavailable, or backed by sample demo data.
  - Keep raw response inspection available for development without exposing secrets or request headers.
- Validation:
  - The frontend can render a polished search result and a polished diagnosis result without knowing whether the data came from sample data or Model Serving.

### Phase 3: Implement the Backend API Boundary

- Status: Pending
- Outcome: The React app has stable API routes that hide Databricks endpoint details.
- Checklist:
  - Add app configuration fields for the retail agent endpoint name, sample data mode, timeout, and any tracing toggle.
  - Add an API route for agentic search submissions.
  - Add an API route for issue diagnosis submissions.
  - Use the existing FastAPI dependency pattern for Databricks workspace access and configuration.
  - Call the Databricks Model Serving endpoint from the backend using Databricks-authenticated access.
  - Pass session and user context in the form expected by the retail agent.
  - Return typed response models with stable operation identifiers for apx OpenAPI generation.
  - Return helpful structured errors for missing endpoint configuration, endpoint cold start or timeout, authentication failure, and malformed endpoint response.
  - Avoid direct Model Serving calls from the browser.
- Validation:
  - The generated frontend client can call both routes.
  - Both routes work with canned demo data.
  - Live endpoint calls are verified when endpoint access is available.

### Phase 4: Recreate the Design Shell and Visual System

- Status: Complete
- Outcome: The app looks and feels like the exported design rather than the default apx starter.
- Checklist:
  - Complete: Replace the placeholder landing route with the `retail/agent` app shell.
  - Complete: Add the sticky header with brand mark, `retail/agent` wordmark, two tabs, profile chip, and reset session action.
  - Complete: Add the footer with demo client and Model Serving endpoint language.
  - Complete: Blend the warm paper background, white paper cards, subtle borders, compact shadows, and restrained accent palette into the existing apx styling.
  - Complete: Use the existing system font stack for general UI text and mono styling for instrumentation.
  - Complete: Use JetBrains Mono-style font utility classes for trace labels, counters, profile tags, tool names, scores, and technical metadata.
  - Complete: Use compact cards with small radii and dense information layout.
  - Complete: Use monogram product placeholders with tinted blocks instead of fake product photography.
  - Complete: Keep the layout responsive: two columns on wide screens, stacked content on narrower screens.
  - Complete: Remove unrelated starter navigation from the root route.
- Validation:
  - Complete: The first screen now follows the design's structure: header, tabbed mode, main column, right rail, and footer.
  - Pending: Desktop and mobile viewport verification in a browser.

### Phase 5: Build Agentic Search

- Status: Complete
- Outcome: The first tab matches the design's search demo and can use live or sample data.
- Checklist:
  - Complete: Add the catalog question card with label, input, ask action, and preset prompt chips.
  - Complete: Include the two design preset prompts: MacBook coding mouse and frequent traveler headphones.
  - Complete: Show the empty answer state before a question is asked.
  - Complete: Animate the answer reveal so the summary, product cards, and paired products appear in sequence.
  - Complete: Render ranked product cards with rank, monogram image, brand, tag, name, rationale, signals, price, rating, review count, and add action when available.
  - Complete: Render the frequently paired graph traversal lane with compact product cards.
  - Complete: Update the profile chip after the simulated memory writes complete.
  - Pending: Gracefully render prose-only live endpoint answers once backend routes are connected.
- Validation:
  - Complete: The search tab can run from both preset chips and typed input using sample data.
  - Pending: Validate live backend response behavior.

### Phase 6: Build Intelligence Surge

- Status: Complete
- Outcome: The right rail delivers the demo's behind-the-scenes story.
- Checklist:
  - Complete: Add the idle intelligence surge panel with a graph-style placeholder.
  - Complete: Show a live indicator while a simulated reveal is in progress.
  - Complete: Show elapsed streaming time during execution.
  - Complete: Show final latency and token count when available.
  - Complete: Render tools used as ordered rows with name, arguments, duration, and result.
  - Complete: Render graph hops as relationship rows with source, edge, and target.
  - Complete: Render knowledge chunks with score, document label, and short excerpt.
  - Complete: Render memory writes with plus markers, key, and value.
  - Complete: Keep reveal timing close to the design when using sample responses.
  - Complete: Make the panel stack on small screens.
- Validation:
  - Complete: The sample-backed panel shows tools, graph relationships, retrieved knowledge, and memory changes without opening logs.
  - Pending: Validate live trace behavior after backend or `retail_agent` structured trace work lands.

### Phase 7: Build Issue Diagnosis

- Status: Complete
- Outcome: The second tab matches the design's support demo and can use live or sample data.
- Checklist:
  - Complete: Add the issue description card with label, input, diagnose action, and preset prompt chips.
  - Complete: Include the two design preset prompts: headphones disconnect during calls and printer showing offline.
  - Complete: Show the empty diagnosis state before a problem is submitted.
  - Complete: Render diagnosis summary and confidence.
  - Complete: Render a symptom-to-cause-to-solution path with directional arrows.
  - Complete: Render recommended actions as a numbered list.
  - Complete: Render compatible alternatives when available.
  - Complete: Add the cited sources rail with idle state, live indicator, source count, source type, source id, title, and excerpt.
  - Complete: Keep the support UI distinct from product search while sharing the local data seam.
- Validation:
  - Complete: The support tab can run from both preset chips and typed input using sample data.
  - Complete: The source rail makes the GraphRAG evidence clear for sample data.
  - Pending: Validate live backend response behavior.

### Phase 8: Session, Reset, and Demo Fallbacks

- Status: In progress
- Outcome: The demo can be run repeatedly without stale or confusing state.
- Checklist:
  - Complete: Generate and maintain a client session identity for each demo session.
  - Complete: Reset local profile chips, active response, progress, query, loading state, and session id when reset session is clicked.
  - Pending: Decide whether reset should also clear server-side agent memory for the demo user.
  - Complete: Make sample demo data explicit through response warnings.
  - Pending: Add live-endpoint fallback warning once backend integration exists.
  - Avoid persisting state in Lakebase unless the user confirms saved sessions, replay, feedback, or cart state.
- Validation:
  - Complete: The presenter can reset and rerun both tabs cleanly with sample data.
  - Pending: Validate behavior when the live endpoint is unavailable through backend integration.

### Phase 9: Databricks App Configuration and Deployment

- Status: Pending
- Outcome: The demo client runs locally and as a Databricks App.
- Checklist:
  - Keep the existing apx build and Databricks bundle workflow unless a better local convention is discovered.
  - Configure the serving endpoint as an app resource or environment-backed setting according to Databricks Apps guidance.
  - Confirm the app service principal can query the retail agent endpoint.
  - Confirm whether user auth is required for the current-user endpoint or personalization.
  - Confirm whether the existing Lakebase resource should remain in the bundle for version one.
  - Use Databricks MCP app lifecycle tools for create, deploy, logs, and status when available.
  - Use the Databricks bundle workflow when MCP app lifecycle tools are unavailable.
  - Verify deployed app logs for startup, configuration, endpoint calls, and fallback behavior.
- Validation:
  - The deployed Databricks App loads, authenticates, calls the endpoint or documented fallback, and has usable logs.

### Phase 10: Quality, Visual Review, and Handoff

- Status: In progress
- Outcome: The demo is repeatable, validated, and ready for stakeholder walkthroughs.
- Checklist:
  - Complete: Run the apx development check through the equivalent local command.
  - Complete: Run the apx production build.
  - Pending: Verify the frontend manually in a browser at desktop and mobile widths.
  - Complete: Compare the implemented UI against the design bundle's key visual requirements during implementation.
  - Complete: Implement the MacBook mouse search preset.
  - Complete: Implement the travel headphones search preset.
  - Complete: Implement the headphones disconnect support preset.
  - Complete: Implement the printer offline support preset.
  - Verify a live endpoint query for one search prompt when endpoint access is available.
  - Verify a live endpoint query for one support prompt when endpoint access is available.
  - Write a short demo script with exact prompts, visible panels, fallback notes, and reset steps.
  - Record known limitations, especially fields that are inferred from prose or backed by sample demo data.
- Validation:
  - The implementation passes checks and build.
  - The UI has been inspected against the design's layout, typography, color, spacing, responsiveness, and animated reveal behavior.

## Completion Criteria

- Status: Pending
- The first screen is the usable `retail/agent` demo, not the apx starter page.
- The app has two tabs: Agentic search and Issue diagnosis.
- Agentic search renders ranked picks, reasons, signals, frequently paired products, profile chips, and intelligence surge details when available.
- Issue diagnosis renders a symptom-to-cause-to-solution path, recommended actions, alternatives, and cited sources when available.
- The right rail or sources rail supports the live streaming feel from the design.
- The visual system follows the design's warm paper palette, compact card style, Helvetica Neue-style UI text, JetBrains Mono instrumentation, and monogram product placeholders.
- The app works through backend API routes and generated frontend client calls.
- The backend can call the Databricks Model Serving endpoint with Databricks app authentication.
- The app has a sample-data fallback path for local demos and endpoint outages.
- The implementation passes apx checks and production build.
- A short demo script exists with reset instructions and known limitations.

## Questions To Resolve

- Should sample demo data fallback be available only locally, or also in the deployed demo if the live endpoint is unavailable?
- Should the current ChatAgent be enhanced to return structured trace data, or should the demo client infer and supplement the prose response?
- Should the backend infer product cards and trace panels from prose when structured data is missing, or should it show prose plus sample demo data where needed?
- Should reset clear only browser state, or should it also clear server-side memory for the demo session?
- Should app-level service principal auth be enough for version one, or is on-behalf-of user auth required for personalization?
- Should the existing Lakebase resource remain in the version-one bundle?
- Should the final implementation include only the two designed tabs, or should later concepts such as comparison, bundle builder, and operator view stay on the roadmap?
- Which Databricks workspace profile and target should be the canonical demo environment?
