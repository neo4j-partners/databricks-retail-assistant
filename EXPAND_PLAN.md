# Graph RAG Expansion Plan for dbx_agent

## Goal

Expand the Databricks agent from a product-search assistant into a full Graph RAG system that can answer questions grounded in reviews, support tickets, and knowledge articles — not just the product catalog. The agent should be able to reason across structured transactions and unstructured text to handle both consumer-facing product discovery and customer-support issue resolution.

---

## What Exists Today

The agent currently has:

- **Product search** via vector embeddings on `Product` nodes (bge-large-en, 1024 dims)
- **Graph traversal** for recommendations across `Product`, `Category`, `Brand`, and `Attribute` nodes
- **Conversation memory** (short-term and long-term) via neo4j-agent-memory
- **Dependency injection** via `ToolRuntime[RetailContext]` — tools receive a shared `MemoryClient` and `session_id`
- **Async bridging** with a persistent background event loop for Databricks Model Serving

The product catalog is the only knowledge the agent can search. It has no access to customer reviews, support history, or troubleshooting documentation.

---

## What We Add

### 1. New Node Types in Neo4j

Using the dataset in `dataset.json` as seed data, add these node types to the graph:

- **Review** — Customer-written product feedback with rating, date, and raw text
- **SupportTicket** — Customer service records with issue description, resolution, and status
- **KnowledgeArticle** — Internal troubleshooting guides, manuals, and FAQs
- **Chunk** — Smaller text blocks extracted from Reviews, Tickets, and Articles, each with a vector embedding for semantic search
- **Feature** — Extracted product attributes mentioned in text (e.g., "Waterproof", "Battery Life", "Zippers")
- **Symptom** — Extracted customer pain points or product failures (e.g., "Leaking base", "Grinding noise")
- **Solution** — Extracted fixes for symptoms (e.g., "Clean burr grinder", "Replace gasket")

### 2. New Relationships

Connect the unstructured world to the structured product catalog:

**Document provenance (text to product):**
- `(Review)-[:REVIEWS]->(Product)`
- `(SupportTicket)-[:ABOUT]->(Product)`
- `(KnowledgeArticle)-[:COVERS]->(Product)`

**Chunking (text to searchable pieces):**
- `(Review)-[:HAS_CHUNK]->(Chunk)`
- `(SupportTicket)-[:HAS_CHUNK]->(Chunk)`
- `(KnowledgeArticle)-[:HAS_CHUNK]->(Chunk)`

**Extracted entities (the reasoning web):**
- `(Chunk)-[:MENTIONS_FEATURE]->(Feature)`
- `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom)`
- `(Chunk)-[:PROVIDES_SOLUTION]->(Solution)`
- `(Symptom)-[:RESOLVED_BY]->(Solution)`
- `(Product)-[:HAS_KNOWN_ISSUE]->(Symptom)`

### 3. New Vector Index

Create a `chunk_embedding` vector index on `Chunk.embedding` (1024 dims, same model as products). This is the primary entry point for Graph RAG — semantic search lands on chunks, then the agent traverses outward to ground its answers.

---

## New Tools for the Agent

All new tools follow the existing pattern: async functions with `ToolRuntime[RetailContext]` injection, no `args_schema`, relative imports.

### Tool: `search_knowledge`

The core Graph RAG retrieval tool. Takes a natural language query, embeds it, and runs vector search against the `chunk_embedding` index. For each matching chunk, traverses back to its source document (Review, Ticket, or Article) and forward to any extracted entities (Features, Symptoms, Solutions). Returns the chunk text, source metadata, and connected entities so the LLM can reason over the full context.

Optional filters: source type (review/ticket/article), product ID, minimum review rating.

### Tool: `get_product_issues`

Given a product ID, traverses the graph to find all known symptoms, their linked solutions, and the source tickets/articles that document them. This gives the agent a structured view of "everything that can go wrong" with a product and how to fix it. Useful for support scenarios where the agent needs to quickly match a customer's complaint to a known resolution.

### Tool: `get_product_feedback`

Given a product ID, retrieves reviews and their extracted features/sentiments. Allows filtering by rating range. This powers the consumer-facing scenario where a customer asks "what do real reviewers say about the zippers?" and the agent can pull grounded answers from actual review text, not just product descriptions.

---

## New Data Loading Script

### Script: `load_knowledge_graph.py`

A new script in `dbx_agent/` (following the pattern of `load_products.py`) that:

1. Reads `dataset.json` from the project root
2. Creates `KnowledgeArticle`, `Review`, and `SupportTicket` nodes with their properties
3. Connects them to existing `Product` nodes via provenance relationships
4. Chunks the text fields (article content, review rawText, ticket issueDescription + resolutionText) into `Chunk` nodes
5. Embeds each chunk using the existing `DatabricksEmbedder`
6. Creates the `chunk_embedding` vector index
7. Extracts `Feature`, `Symptom`, and `Solution` entities from chunks (using an LLM call to the configured endpoint, or a simpler keyword/pattern approach for the initial version)
8. Creates the entity relationships (`MENTIONS_FEATURE`, `REPORTS_SYMPTOM`, `PROVIDES_SOLUTION`, `RESOLVED_BY`, `HAS_KNOWN_ISSUE`)

Entity extraction is the most complex step. For the initial version, we could use a structured LLM call (send each chunk to the LLM with a prompt asking it to extract features, symptoms, and solutions as JSON). This keeps the ingestion pipeline simple while producing high-quality entities.

---

## Changes to Existing Files

### `agent.py`

- Import the new tools and add them to the tool list passed to `create_prototype_agent()`
- Update the system prompt to tell the agent about its new Graph RAG capabilities — it can now search knowledge articles, reviews, and support tickets, and should use `search_knowledge` when a question involves troubleshooting, product feedback, or issues

### `config.py`

- Add any new config values if needed (e.g., chunk size, overlap, vector index name for chunks)

### `deploy.py`

- Add the new tool files to the `code_files` list so MLflow packages them into the deployment

### `context.py`

- No changes expected — the existing `RetailContext` with `MemoryClient` and `session_id` should be sufficient since the new tools will query Neo4j through the same client

---

## How the Agent Uses This

### Scenario A: Consumer Product Discovery

A customer asks: "I want a tent that holds up in heavy rain — do real reviewers say the zippers work well?"

1. Agent calls `search_products` to find tents (existing tool)
2. Agent calls `search_knowledge` with the query about zippers and rain — vector search hits chunks from reviews and articles about the AquaShield tent
3. Agent traverses from matching chunks to their source Reviews, filters to high-rating ones, and reads the actual reviewer text
4. Agent synthesizes a grounded answer citing real feedback

### Scenario B: Customer Support Issue Resolution

A customer says: "My EspressoMaster is making a grinding noise and no coffee comes out."

1. Agent calls `search_knowledge` — vector search hits chunks from the troubleshooting article (KA-001) and past support ticket (T-001)
2. From the chunks, the agent traverses to `Symptom {name: "Grinding Noise"}` and then `RESOLVED_BY` to `Solution {name: "Clean Burr Grinder"}`
3. Agent provides the step-by-step fix from the knowledge article, grounded in the actual documentation
4. If the customer says it didn't work, the agent can see from the graph that ticket T-006 is still open for the same recurring issue, suggesting the problem may need escalation

### Scenario C: Pre-Sales Expectation Management

A customer asks: "Can the SolarFlare PowerBank charge my phone purely from solar?"

1. Agent calls `search_knowledge` — hits chunks from the manual (KA-025), negative review (R-026), and resolved ticket (T-025)
2. The agent sees the `Solution` entity explaining the solar panel is for emergency trickle charging only (50 hours for full charge)
3. Agent gives an honest, grounded answer synthesized from the manual and real customer experiences

---

## Scope and Constraints

- All new code lives in `dbx_agent/` and follows its conventions (relative imports, no `test_` prefixed files, async-first, `ToolRuntime` injection)
- Uses the same `DatabricksEmbedder` (bge-large-en, 1024 dims) — no new embedding models
- Uses the same Neo4j instance — just adds new node labels, relationships, and one new vector index
- The `dataset.json` file provides the seed data (5 products, 30 reviews, 30 tickets, 30 knowledge articles)
- Entity extraction during ingestion can start simple (LLM-based or even manually curated for the seed data) and be refined later
- No changes to the local FastAPI backend — this expansion is Databricks-agent only
