# Proposal: Adding GraphRAG Entity Extraction and Advanced Retrievers to the Retail Assistant

## Context

The retail assistant currently loads 21 products into Neo4j with Category, Brand, and Attribute nodes, plus 252 unstructured documents — 84 knowledge articles, 84 support tickets, and 84 reviews. These documents are stored as nodes (KnowledgeArticle, SupportTicket, Review) with relationships to their products (COVERS, ABOUT, REVIEWS), but the text inside them is not chunked, embedded, or analyzed. The agent can look up a product and find its related articles or tickets, but it cannot search across all documents semantically, and it cannot discover that the same symptom or solution appears across different products, brands, or document types.

The `databricks-neo4j-lab` workshop demonstrates how to chunk a document, embed the chunks, store them in Neo4j with vector and fulltext indexes, and query them using various retriever patterns (VectorRetriever, VectorCypherRetriever, HybridRetriever, HybridCypherRetriever). Those techniques should be applied here — but this project should go further by adding entity extraction, which the lab does not do. The lab's retrievers fall back on brittle keyword matching (checking if a chunk's text contains the word "Engine") because there are no extracted entity nodes to traverse. This proposal describes how to build the entity layer that makes GraphRAG genuinely useful.

---

## 1. Expanding the Sample Data for Entity Extraction

### Why the current data needs enrichment

The 252 documents already contain natural entity references — symptoms, product features, and solutions — but they are mostly siloed within a single product. The knowledge articles for the Nike Pegasus talk about React foam; the articles for the Adidas Ultraboost talk about Boost foam; but neither mentions the other. Entity extraction is only compelling as a demo when the same entity appears across multiple documents from different sources, because that is what creates cross-document connections that no vector search can reliably surface.

### Cross-product entity clusters to strengthen

The existing data has a few natural overlaps that should be made more explicit, plus several new clusters that should be added. The goal is 8-10 entity clusters where the same Feature, Symptom, or Solution appears across at least 3 products.

**Cluster 1 — Outsole separation / peeling.** Currently appears in the Ultraboost data (KA-008 "Continental Outsole Peeling", T-006 "outsole peeling off at the toe area", R-007 "outsole started peeling from the midsole"). The Pegasus ticket T-004 already mentions "outsole separating from the midsole." Enrich the Ghost 16 and Air Max 90 documents to also mention outsole separation as a known wear issue, so the extracted Symptom node "outsole separation" connects across 4 products and 3 brands.

**Cluster 2 — Midsole cushion degradation.** The Pegasus article KA-003 describes React foam going flat. The Ultraboost, Nimbus, and Ghost 16 each have their own cushioning technology (Boost, FF Blast Plus, DNA Loft v2). Enrich articles and reviews to cross-reference these technologies by name, so that a Symptom "cushion responsiveness loss" connects to Feature nodes for each midsole technology across all running shoe brands.

**Cluster 3 — Yellowing and oxidation.** Already appears in Ultraboost (KA-007 "Boost Midsole Turning Yellow") and Air Max 90 (KA-024 "Yellowing of the White Midsole"). Both use the same baking soda + peroxide solution. Enrich the Stan Smith data (white leather also yellows) and the NB-574 (white midsole). The shared Solution "baking soda and peroxide paste" connects four products across three brands through the same cosmetic issue.

**Cluster 4 — Moisture wicking degradation from fabric softener.** The Dri-FIT shirt articles (KA-034, KA-035) explicitly blame fabric softener for destroying wicking. The Adidas running shorts ticket T-039 and the ColdGear articles should also reference fabric softener as a root cause. The shared Symptom "wicking performance loss" and Solution "vinegar wash, no fabric softener" connect all three moisture-management technologies (Dri-FIT, AEROREADY, ColdGear).

**Cluster 5 — Suede and leather water damage.** The NB-990v6 (KA-011 "Suede Staining and Water Marks") and NB-574 (KA-031 "Suede Panels Staining from Rain") already share this. Add water damage references to the Stan Smith leather care articles. The shared Solution "suede protector spray" and "air dry at room temperature" connects all three products.

**Cluster 6 — Insole slippage and arch issues.** The NB-574 article KA-032 describes insoles sliding out of place. ASICS Nimbus ticket T-016 mentions insole issues. The Nike running socks article KA-047 describes socks bunching under the arch. These share a common Symptom around fit and support under the foot, with related Solutions (double-sided tape, correct sizing, arch band support).

**Cluster 7 — Break-in period frustration.** Stan Smith leather (KA-026 "1 week break-in"), NB-990v6 ENCAP midsole (KA-012 "20-30 miles"), and ColdGear compression fit (T-044 "feels too tight at first"). Different materials, same customer frustration pattern. A shared Symptom "product feels uncomfortable initially" with product-specific Solutions creates a useful cross-category connection.

**Cluster 8 — Odor retention in synthetic materials.** Dri-FIT shirt (KA-034 "odor retention"), running shorts (T-039 liner bacterial buildup), hydration belt flasks (KA-052 "mildew smell"), and foam roller (off-gassing). All caused by synthetic materials trapping bacteria or residue. Shared Solutions include vinegar soaking and baking soda treatment.

**Cluster 9 — Waterproofing and weather protection.** REI Half Dome tent (KA-066 "1500mm PU coating"), Kelty Cosmic sleeping bag (KA-078 "DriDown hydrophobic treatment"), NB-990v6 suede (KA-011 "not treated for water resistance"). A shared Feature "weather/water resistance" with varying levels across categories connects outdoor gear to footwear through a common customer concern.

**Cluster 10 — Elastic and material degradation over time.** Nike running socks (KA-048 "elastic losing stretch"), resistance bands (KA-059 "latex degrades over time"), foam roller (KA-055 "EVA foam cracking"), hydration belt flask caps (KA-051 "gasket cracks"). A shared Symptom "material degradation from age/UV/heat" with a common Solution pattern "inspect regularly and replace when worn."

### How to enrich the data

Edit the `content`, `issue_description`, `resolution_text`, and `raw_text` fields in `product_knowledge.py` to include more explicit cross-product references. The total document count (252) is sufficient — the density of entity references within each document is what needs to increase.

**Before (KA-003):**

> Symptom: The React foam midsole feels less responsive after 300+ miles. Solution: This is expected wear. Running shoes should be replaced every 300-500 miles. Check the outsole — if the tread pattern is worn smooth, it is time for a new pair.

**After (enriched):**

> Symptom: The React foam midsole feels less responsive and flat after 300+ miles of use. This loss of cushion responsiveness is common across all foam midsole technologies including React, Boost, FF Blast Plus, and DNA Loft — each degrades at different rates depending on runner weight and running surface. Solution: Running shoes should be replaced every 300-500 miles regardless of brand. Check the outsole tread pattern — if worn smooth, it is time for a new pair. Rotating between two pairs of daily trainers extends the life of both by allowing the foam cells to recover between runs.

The enriched version contains extractable entities: Feature "React foam midsole", Feature "Boost", Feature "FF Blast Plus", Feature "DNA Loft", Symptom "cushion responsiveness loss", Solution "replace every 300-500 miles", Solution "rotate between two pairs."

### Implementation Status — COMPLETE

All 10 entity clusters have been enriched in `dbx_agent/data/product_knowledge.py`. The document count remains 252 (84 KA, 84 T, 84 R) — only the text content was modified to add cross-product entity references.

| Cluster | Documents Enriched |
|---|---|
| 1. Outsole separation | KA-008, KA-020, T-004, T-006, T-018, R-007 |
| 2. Cushion degradation | KA-003, KA-012, KA-015, T-001, R-003, R-010, R-013, R-017 |
| 3. Yellowing/oxidation | KA-007, KA-024, KA-027, T-005, T-022, R-006, R-024 |
| 4. Wicking degradation | KA-035, KA-037, KA-041, KA-045, T-034, T-039, T-043, T-044, R-034, R-035, R-042 |
| 5. Suede water damage | KA-011, KA-031, T-009, T-029, R-011, R-031 |
| 6. Insole slippage | KA-032, KA-015, T-016, T-030, R-032 |
| 7. Break-in frustration | KA-026, KA-012, T-010, T-026, T-043, R-010, R-026, R-042 |
| 8. Odor retention | KA-037, KA-052, T-050, R-035, R-052 |
| 9. Waterproofing | KA-066, KA-078, KA-071, T-065, T-077, R-067, R-071, R-079 |
| 10. Material degradation | KA-048, KA-055, KA-059, T-046, T-053, T-057, R-047, R-055, R-059 |

---

## 2. Second Data Load Step: Chunking, Embedding, and Entity Extraction

### Where it fits

The current `load_products.py` creates the structured graph: Product, Category, Brand, Attribute, KnowledgeArticle, SupportTicket, and Review nodes with all their relationships, plus a vector index on Product embeddings. A new script — `load_graphrag.py` — should run after `load_products.py` and add the semantic layer without touching any existing nodes. It only creates new Chunk, Feature, Symptom, and Solution nodes with relationships.

### Stage 1 — Chunk the existing documents

Pull the text content from the 252 existing document nodes: `content` from KnowledgeArticle, `issue_description` concatenated with `resolution_text` from SupportTicket, and `raw_text` from Review. Each document is already short (1-3 paragraphs), so most will produce one or two chunks. For knowledge articles that have distinct "Symptom" and "Solution" sections, split at section boundaries rather than by fixed character count. For reviews, each review is already one chunk.

Create Chunk nodes with a chunk ID, the text, the source type (article, ticket, or review), and a position index. Connect them to their source documents:

- KnowledgeArticle -[HAS_CHUNK]-> Chunk
- SupportTicket -[HAS_CHUNK]-> Chunk
- Review -[HAS_CHUNK]-> Chunk
- Chunk -[NEXT_CHUNK]-> Chunk (for multi-chunk documents, preserving reading order)

This parallels the Document → Chunk → NEXT_CHUNK pattern from the aircraft lab's Notebook 03.

### Stage 2 — Embed chunks

Generate vector embeddings for each chunk using the same Databricks Foundation Model API already used for product embeddings (databricks-bge-large-en, 1024 dimensions). Store embeddings on Chunk nodes. Create two indexes:

- A vector index (`chunk_embedding`) for semantic similarity search
- A fulltext index (`chunkText`) for keyword search

This enables both vector and hybrid retriever patterns. The retail project now has two vector indexes in the same Neo4j database — one on Products for product search, one on Chunks for document search — demonstrating that Neo4j serves as both the vector store and the knowledge graph with no separate vector database needed.

### Stage 3 — Extract entities using an LLM

For each chunk, call a Databricks-hosted LLM (Meta Llama 3.3 70B via the Foundation Model API) with a structured extraction prompt. The LLM should identify three types of entities:

- **Features**: Product technologies, materials, or attributes mentioned (React foam midsole, Continental rubber outsole, Dri-FIT moisture wicking, DriDown hydrophobic treatment)
- **Symptoms**: Problems, complaints, or issues described (cushion feels flat, outsole peeling, fabric pilling, GPS takes too long to lock)
- **Solutions**: Fixes, recommendations, or resolutions given (replace every 300-500 miles, use heel-lock lacing, wash with vinegar, apply suede protector)

The prompt instructs the LLM to return structured JSON with a short canonical name for each entity and the exact text mention from the source. Parse the response and create or merge entity nodes in the graph.

With approximately 252 chunks (most documents produce one chunk), this requires about 252 LLM calls. At typical latency for a Databricks Foundation Model endpoint, the full extraction takes roughly 5-10 minutes.

### Stage 4 — Link entities to chunks and products

Connect extracted entities to their source chunks:

- Chunk -[MENTIONS_FEATURE]-> Feature
- Chunk -[REPORTS_SYMPTOM]-> Symptom
- Chunk -[PROVIDES_SOLUTION]-> Solution

Create cross-entity relationships when a chunk contains both a symptom and its solution:

- Symptom -[RESOLVED_BY]-> Solution

Connect features to products by traversing through the source document:

- Product -[HAS_FEATURE]-> Feature (derived from Product <-[COVERS]- KnowledgeArticle -[HAS_CHUNK]-> Chunk -[MENTIONS_FEATURE]-> Feature)

### Stage 5 — Basic entity resolution

The same symptom may be extracted with different names from different documents: "outsole peeling", "sole separating from midsole", "outsole detaching." The pipeline should demonstrate a simple deduplication step: embed all entity names, find pairs with cosine similarity above a threshold, and merge them into a single canonical node. This ensures that graph traversals work correctly across documents that describe the same issue in different words.

### Graph schema after this step

The graph now has four layers:

1. **Structured product layer** (existing): Product, Category, Brand, Attribute with IN_CATEGORY, MADE_BY, SIMILAR_TO, BOUGHT_TOGETHER, HAS_ATTRIBUTE
2. **Document layer** (existing): KnowledgeArticle, SupportTicket, Review with COVERS, ABOUT, REVIEWS
3. **Chunk layer** (new): Chunk nodes with HAS_CHUNK and NEXT_CHUNK, plus vector and fulltext indexes
4. **Entity layer** (new): Feature, Symptom, Solution with MENTIONS_FEATURE, REPORTS_SYMPTOM, PROVIDES_SOLUTION, RESOLVED_BY, HAS_FEATURE

---

## Open Questions on Section 2

### Stage 1 — Chunking

- **Chunking strategy for support tickets:** The proposal says to concatenate `issue_description` with `resolution_text` for tickets. Should these be kept as separate chunks instead? They represent different intent (problem vs. fix), and keeping them separate could produce cleaner entity extraction — one chunk yields Symptoms, the other yields Solutions. What's the rationale for combining them?


**ANSWER** : Keep the separate 

- **Section-boundary splitting for knowledge articles:** How are "Symptom" and "Solution" sections detected? Is there a consistent delimiter in the `content` field (e.g., "Symptom:" / "Solution:" prefixes), or does this require heuristic parsing? If the format varies across articles, what's the fallback?

**ANSWER** : Are the knowldge articles even long enough to need splitting? I think they are pretty small?


- **Chunk size bounds:** The proposal says most documents produce 1-2 chunks. Is there a max chunk size? Some enriched articles (after Section 1 edits) could get long enough that a single chunk exceeds the embedding model's token limit or dilutes the entity extraction quality. Should there be a character/token cap with overlap?

**ANSWER** : section 1 has been implemented - see if max chunk size is still a concern 

- **Chunk ID scheme:** What's the chunk ID format? Something like `{source_type}-{doc_id}-{position}` (e.g., `ka-003-0`, `ka-003-1`)? This matters for debugging and for the NEXT_CHUNK ordering.

**ANSWER** : The proposed ID schema works great .

### Stage 2 — Embedding

- **Embedding model token limit:** `databricks-bge-large-en` has a 512-token input limit. After enrichment, some article chunks could exceed that. Should chunks be truncated, or should Stage 1 enforce a max size that fits within the embedding window?
- **Batch embedding:** The current `load_products.py` embeds products one at a time. With ~252+ chunks, should the new script use batch embedding calls for throughput? Does the Databricks Foundation Model API support batch requests, or should we just parallelize single calls?
- **Fulltext index configuration:** The proposal mentions a `chunkText` fulltext index. Which fields does it index — just the chunk text, or also the source document ID and source type? Should it use the default analyzer or a custom one (e.g., English stemming)?

### Stage 3 — Entity Extraction

- **Extraction prompt design:** This is the most critical piece and the proposal doesn't include it. What does the prompt look like? Specifically:
  - Does it use few-shot examples? Given that entity naming consistency is critical for Stage 5, few-shot examples that demonstrate canonical naming could reduce dedup work.
  - Does it ask the LLM to assign a canonical name *and* capture the verbatim mention, or just one of these?
  - Does it enforce the Feature/Symptom/Solution taxonomy strictly, or allow the LLM to suggest a type?
- **Entity naming consistency:** "React foam midsole" vs. "React foam" vs. "Nike React" — how much normalization does the prompt enforce? If the prompt doesn't tightly constrain naming, Stage 5 dedup has a much harder job. Should the prompt include a reference list of known entity names to steer toward?
- **Structured output parsing:** The proposal says the LLM returns JSON. What happens on malformed JSON? Retry? Skip the chunk? Log and continue? At 252 calls, even a 5% failure rate means ~13 chunks with no entities.
- **LLM cost and rate limits:** 252 calls to Llama 3.3 70B — is there a rate limit on the Databricks Foundation Model API endpoint that could cause throttling? Should the script include backoff/retry logic?
- **Entity granularity:** Should "baking soda and hydrogen peroxide paste" be one Solution entity or two (the paste + the application method "scrub gently, leave in sunlight")? The proposal's examples suggest compound solutions. What's the guidance on granularity — one entity per distinct actionable step, or one per conceptual solution?

### Stage 4 — Linking

- **HAS_FEATURE derivation:** The proposal describes deriving Product -[HAS_FEATURE]-> Feature by traversing Product ← COVERS ← KnowledgeArticle → HAS_CHUNK → Chunk → MENTIONS_FEATURE → Feature. Should this also work through SupportTicket (ABOUT) and Review (REVIEWS) paths? A feature mentioned only in a review but not in a knowledge article would be missed otherwise.
- **RESOLVED_BY creation logic:** "When a chunk contains both a symptom and its solution" — what if a chunk mentions Symptom A and Solution B, but they're unrelated (e.g., the article lists multiple issues)? Does the script assume all symptoms and solutions in the same chunk are related, or does the extraction prompt need to explicitly pair them?
- **Relationship properties:** Should MENTIONS_FEATURE, REPORTS_SYMPTOM, etc. carry any properties — like the verbatim mention text, a confidence score from the LLM, or the chunk position? This could be useful for debugging and for weighted retrieval.

### Stage 5 — Entity Resolution

- **Similarity threshold:** What cosine similarity threshold triggers a merge? Too low and you get false merges ("outsole peeling" ≠ "insole slipping"); too high and you miss valid duplicates ("outsole peeling" ≈ "sole separating from midsole"). Is there a planned approach for tuning this — manual review of a sample, or a fixed threshold?
- **Merge strategy:** When two entities merge, which name becomes canonical? The one that appears more frequently? The shorter one? The first one encountered? Does the merged node retain all original names as aliases?
- **Cross-type dedup:** Can a Symptom and a Feature ever be the same entity extracted differently? E.g., "moisture wicking" could be extracted as a Feature in one chunk and as a Symptom ("wicking performance loss") in another. Is cross-type resolution in scope, or only within-type?
- **Entity resolution at scale:** Embedding all entity names and computing pairwise similarity is O(n²). With ~50-100 entities this is trivial, but should the proposal note the approach and confirm the expected entity count to justify brute-force pairwise comparison?

### General / Cross-Cutting

- **Idempotency:** Can `load_graphrag.py` be run multiple times safely? If re-run after data enrichment, does it clear and rebuild the chunk/entity layers, or does it merge incrementally? The proposal says it "adds the semantic layer without touching existing nodes" — but what about re-runs?
- **Error recovery:** If the script fails mid-way (e.g., after chunking but before entity extraction), can it resume from where it left off, or does it need to start over?
- **Which package does this live in?** The proposal says `load_graphrag.py` but doesn't specify whether it goes in `sample_agent/scripts/` or `dbx_agent/` or somewhere else. Given the project structure, which agent does this belong to?

---

## 3. Expanded GraphRAG Retriever Examples

### What the lab currently demonstrates

The aircraft lab shows four retriever patterns: VectorRetriever (pure semantic search), VectorCypherRetriever (vector search plus Cypher enrichment), HybridRetriever (vector plus fulltext keyword search), and HybridCypherRetriever (hybrid plus Cypher). These operate within the document-chunk layer. The Cypher enrichment reaches into the structured graph but only through keyword matching (checking if chunk text CONTAINS system names).

### Proposed retriever examples for the retail assistant

Each example follows the same format: state the user question, show what plain vector search returns, show what entity-aware retrieval adds, and highlight the cross-document connections that only the entity layer makes possible.

**Example 1 — Entity-Aware Vector Retrieval: "My running shoes feel flat and unresponsive. What should I do?"**

A plain VectorRetriever finds the 3-5 chunks most semantically similar to the query. It likely returns chunks from the Nike Pegasus articles about React foam degradation — the closest semantic match. It misses the broader context.

An entity-aware VectorCypherRetriever starts with the same vector search but then traverses from the matched chunks through their extracted entities. It follows Chunk → REPORTS_SYMPTOM → Symptom ("cushion responsiveness loss") → RESOLVED_BY → Solution to find the recommended fix. Then it follows Symptom ← REPORTS_SYMPTOM ← Chunk (other chunks) to find that this same symptom is reported across Ultraboost, Nimbus, and Ghost 16 documents with brand-specific solutions for each. The agent can now tell the customer: "This is normal midsole wear. All foam technologies degrade over 300-500 miles. Here's what to do for your specific shoe." No amount of vector similarity alone would reliably surface a Brooks Ghost review when the query matched a Nike Pegasus article.

**Example 2 — Cross-Document Entity Traversal: "Is the Continental outsole on the Ultraboost durable?"**

A VectorCypherRetriever with entity traversal finds all chunks that mention the Feature "Continental rubber outsole", regardless of which document type they come from. It pulls together: the knowledge article describing the warranty process (KA-008), the support ticket where a customer got a replacement (T-006), and the 1-star review complaining about peeling after 3 months (R-007). It also finds any enriched mentions from other products that share the same outsole issue. The agent synthesizes: "The Continental outsole has known separation issues reported by multiple customers. If your pair is within 6 months of purchase, Adidas offers warranty replacement. For minor separation, shoe adhesive provides a temporary fix."

**Example 3 — Symptom-First Retrieval (Graph-First, No Vector Search): "What are the most common problems with running shoes?"**

Instead of starting with vector search, this retriever starts with a pure graph query. It traverses from all Symptom nodes back through REPORTS_SYMPTOM to their Chunks, then through the source documents to their Products, filtering to products in the Running Shoes category. It counts how many documents report each symptom and ranks them. The result is a structured answer: "The top issues are (1) cushion degradation after 300+ miles, reported across all 5 running shoe brands, (2) outsole separation, reported for Ultraboost and Pegasus, (3) heel blistering, reported for Pegasus and Nimbus, (4) sizing runs narrow, reported for Pegasus and Ghost." No embedding is needed — the graph structure itself answers the question.

**Example 4 — Causal Chain Retrieval: "Will my Nike Pegasus outsole peel like my friend's Ultraboost did?"**

The retriever uses vector search to find chunks about outsole peeling, then traverses through the shared Symptom entity to check whether other products have the same issue. It follows Symptom ("outsole separation") ← REPORTS_SYMPTOM ← Chunk ← HAS_CHUNK ← (source document) → COVERS/ABOUT/REVIEWS → Product to find every product that has a document mentioning this symptom. If the enriched Pegasus data includes outsole separation mentions, the agent gives a grounded answer: "Yes, outsole separation has been reported for the Pegasus as well, though less frequently than for the Ultraboost. The Pegasus uses a different outsole compound, so the failure pattern may differ." If no Pegasus documents mention it, the agent can honestly say: "There are no reports of outsole separation for the Pegasus in our data."

**Example 5 — Solution Discovery via Feature Similarity: "How do I clean yellowed foam on my shoes?"**

The retriever finds chunks about yellowing through vector search, then traverses Chunk → REPORTS_SYMPTOM → Symptom ("yellowing / oxidation") → RESOLVED_BY → Solution to find all known fixes. It also follows Solution ← PROVIDES_SOLUTION ← Chunk ← HAS_CHUNK ← (source) → Product to find which products each solution applies to. The result: "Yellowing affects both Ultraboost (Boost foam) and Air Max 90 (midsole and Air unit). The same cleaning method works for both: apply a paste of baking soda and hydrogen peroxide, scrub gently, and leave in indirect sunlight for 2-3 hours."

### How these examples demonstrate progressive capability

The five examples form a progression:

1. Vector search enhanced by entity context (Example 1)
2. Entity traversal across document types (Example 2)
3. Pure graph retrieval with no vector search (Example 3)
4. Comparative reasoning across products through shared entities (Example 4)
5. Solution-centric retrieval starting from a symptom (Example 5)

Each step adds a capability that the previous step cannot provide. Together they show why entity extraction transforms a document store into a reasoning graph.

---

## 4. Key Technologies to Highlight

### Technologies already in use that should remain prominent

- **Neo4j Aura** as the graph database for both the structured product catalog and the GraphRAG entity layer
- **Databricks Foundation Model APIs** for embeddings (databricks-bge-large-en, 1024 dimensions) and LLM inference (databricks-meta-llama-3-3-70b-instruct) — used for both product embedding and the new entity extraction
- **Databricks Unity Catalog** for data governance across lakehouse tables and data volumes
- **AI/BI Genie Spaces** for natural language querying of the transaction, customer, and inventory tables in the lakehouse
- **Databricks AgentBricks** for the multi-agent supervisor that routes between the Genie Lakehouse Agent and the Neo4j KG Agent
- **neo4j-agent-memory** for persistent structured memory backed by the same Neo4j instance

### New technologies to highlight

**LLM-Powered Structured Entity Extraction.** This is the key new capability. It demonstrates using a Databricks-hosted LLM as a structured data extraction tool — prompting it with chunk text and a JSON schema, receiving back typed entities with canonical names. This is the pattern that fills the gap in the current approach: instead of brittle keyword matching to connect chunks to the structured graph, entities create explicit, traversable relationships. Participants can reuse this extraction pattern in any domain — retail, healthcare, legal, manufacturing.

**Multiple Neo4j Vector Indexes.** The current project has one vector index on Product nodes. The new pipeline adds a second on Chunk nodes. Running both in the same Neo4j database demonstrates that Neo4j serves as both the vector store and the knowledge graph — no separate Pinecone, Weaviate, or ChromaDB instance is needed. This is a significant architectural simplification for production systems.

**Hybrid Search for Retail.** The aircraft lab demonstrates hybrid search with maintenance terminology. Applying it to retail data makes the concept more accessible. A query like "React foam peeling after 300 miles" benefits from hybrid search: the fulltext component catches "React foam" as an exact match while the vector component finds semantically similar cushioning degradation across other brands that use different terminology.

**neo4j-graphrag Retriever Library.** The lab uses VectorRetriever, VectorCypherRetriever, HybridRetriever, and HybridCypherRetriever from the neo4j-graphrag Python library. The retail demo should reuse these same classes but with entity-enriched Cypher queries that traverse through Feature, Symptom, and Solution nodes. Showing the same retriever classes with increasingly sophisticated Cypher creates a clear progression from basic to advanced GraphRAG.

**Databricks Workflows (Production Callout).** The `load_products.py` and `load_graphrag.py` scripts could be orchestrated as a Databricks Workflow that runs when new knowledge articles or support tickets are added. While the demo uses scripts for interactive exploration, pointing out how this pipeline would be operationalized via Workflows connects the workshop to production deployment patterns.

---

## Summary

The expansion adds three concrete things to the retail assistant:

1. **Richer sample data** — Strengthen cross-product entity references in the existing 252 documents so that entity extraction creates meaningful connections across products, brands, and categories.

2. **A new loading script** (`load_graphrag.py`) — A 5-stage pipeline that chunks the existing documents, embeds the chunks, extracts Feature/Symptom/Solution entities using an LLM, links entities to chunks and products, and resolves duplicate entities. Runs after `load_products.py` and adds the semantic layer to the graph.

3. **Five retriever examples** — Progressive demonstrations from entity-aware vector search to pure graph-first retrieval, each showing what the entity layer adds that plain vector search cannot provide. Uses the same neo4j-graphrag retriever classes as the aircraft lab but with Cypher queries that traverse the entity layer.

The key technology highlight is LLM-powered entity extraction — the bridge between raw document text and a structured knowledge graph that agents can reason over.
