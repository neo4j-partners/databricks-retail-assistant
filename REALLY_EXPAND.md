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

The 252 documents are all short — the longest knowledge article is ~200 tokens, the longest ticket is ~210 tokens combined, and the longest review is ~90 tokens. No size-based splitting is needed; everything fits well within the 512-token embedding model limit.

**Chunking rules:**

- **Knowledge articles** (84): One chunk per article. No splitting — even the enriched articles are well under 200 tokens.
- **Support tickets** (84): Two chunks per ticket — `issue_description` and `resolution_text` as separate chunks. This preserves the semantic distinction between problem and fix, producing cleaner entity extraction (issue chunks yield Symptoms, resolution chunks yield Solutions).
- **Reviews** (84): One chunk per review.

This produces approximately **336 chunks** (84 + 168 + 84).

Create Chunk nodes with a chunk ID, the text, and the source type. Chunk IDs follow the format `{source_type}-{doc_id}-{position}` (e.g., `ka-003-0`, `t-004-0`, `t-004-1`, `r-007-0`). Connect them to their source documents:

- KnowledgeArticle -[HAS_CHUNK]-> Chunk
- SupportTicket -[HAS_CHUNK]-> Chunk
- Review -[HAS_CHUNK]-> Chunk
- Chunk -[NEXT_CHUNK]-> Chunk (for ticket chunks only, linking issue to resolution)

### Stage 2 — Embed chunks

Generate vector embeddings for each chunk sequentially using the same Databricks Foundation Model API already used for product embeddings (databricks-bge-large-en, 1024 dimensions). Store embeddings on Chunk nodes. Create two indexes:

- A vector index (`chunk_embedding`) for semantic similarity search
- A fulltext index (`chunkText`) on the chunk text field, using an English analyzer for stemming

This enables both vector and hybrid retriever patterns. The retail project now has two vector indexes in the same Neo4j database — one on Products for product search, one on Chunks for document search — demonstrating that Neo4j serves as both the vector store and the knowledge graph with no separate vector database needed.

### Stage 3 — Extract entities using an LLM

For each chunk, call a Databricks-hosted LLM (Meta Llama 3.3 70B via the Foundation Model API) with a structured extraction prompt. The LLM should identify three types of entities:

- **Features**: Product technologies, materials, or attributes mentioned (React foam midsole, Continental rubber outsole, Dri-FIT moisture wicking, DriDown hydrophobic treatment)
- **Symptoms**: Problems, complaints, or issues described (cushion feels flat, outsole peeling, fabric pilling, GPS takes too long to lock)
- **Solutions**: Fixes, recommendations, or resolutions given (replace every 300-500 miles, use heel-lock lacing, wash with vinegar, apply suede protector)

The prompt instructs the LLM to return structured JSON with just a short canonical name for each entity (no verbatim mention needed — keeps it simple). The prompt includes 2-3 few-shot examples covering one Feature, one Symptom, and one Solution to drive consistent canonical naming. The taxonomy is a guide, not a strict constraint — if the LLM is unsure whether something is a Feature or a Symptom, that's fine; the graph traversals work either way. One entity per conceptual item (e.g., "baking soda and peroxide paste" is one Solution, not split into sub-steps).

Parse the JSON response. On malformed JSON, log a warning and skip the chunk — at 336 calls, a few failures don't affect the demo.

With approximately 336 chunks, this requires about 336 LLM calls. At typical latency for a Databricks Foundation Model endpoint, the full extraction takes roughly 5-10 minutes.

**No entity resolution / dedup stage.** The enriched data in Section 1 was written with intentionally consistent entity terminology across clusters, and the extraction prompt uses few-shot examples to steer toward canonical names. If a few near-duplicates slip through, they don't break the demo. This avoids the complexity of embedding-based pairwise similarity, threshold tuning, and merge logic.

### Stage 4 — Link entities to chunks and products

Connect extracted entities to their source chunks (no properties on the relationships — keep it simple):

- Chunk -[MENTIONS_FEATURE]-> Feature
- Chunk -[REPORTS_SYMPTOM]-> Symptom
- Chunk -[PROVIDES_SOLUTION]-> Solution

Connect entities to products by traversing through the source documents. This works through all three document types:

- Product -[HAS_FEATURE]-> Feature (derived from Product ← COVERS/ABOUT/REVIEWS ← source document → HAS_CHUNK → Chunk → MENTIONS_FEATURE → Feature)
- Product -[HAS_SYMPTOM]-> Symptom (same traversal through REPORTS_SYMPTOM)
- Product -[HAS_SOLUTION]-> Solution (same traversal through PROVIDES_SOLUTION)

### Graph schema after this step

The graph now has four layers:

1. **Structured product layer** (existing): Product, Category, Brand, Attribute with IN_CATEGORY, MADE_BY, SIMILAR_TO, BOUGHT_TOGETHER, HAS_ATTRIBUTE
2. **Document layer** (existing): KnowledgeArticle, SupportTicket, Review with COVERS, ABOUT, REVIEWS
3. **Chunk layer** (new): Chunk nodes with HAS_CHUNK and NEXT_CHUNK, plus vector and fulltext indexes
4. **Entity layer** (new): Feature, Symptom, Solution with MENTIONS_FEATURE, REPORTS_SYMPTOM, PROVIDES_SOLUTION, HAS_FEATURE, HAS_SYMPTOM, HAS_SOLUTION

### Implementation Status — COMPLETE

Implemented in `dbx_agent/load_graphrag.py`. Run with `uv run python -m dbx_agent.load_graphrag` after `load_products.py`.

| Stage | What it does | Details |
|---|---|---|
| 1. Chunk | Creates 336 Chunk nodes from 252 documents | KA: 1 chunk each (84). Tickets: 2 chunks each — issue + resolution (168). Reviews: 1 chunk each (84). IDs: `ka-001-0`, `t-001-0`/`t-001-1`, `r-001-0`. HAS_CHUNK + NEXT_CHUNK relationships. |
| 2. Embed | Embeds chunks via Databricks Foundation Model API | Sequential embedding (batch_size=100 per API call). Vector index `chunk_embedding` (1024 dims, cosine). Fulltext index `chunkText` (English analyzer). |
| 3. Extract | Extracts Feature/Symptom/Solution entities via Llama 3.3 70B | 3 few-shot examples. Canonical names only. MERGE entity nodes, CREATE chunk→entity relationships. Log and skip on malformed JSON. |
| 4. Link | Derives Product-level entity relationships | Traverses Product ← doc → Chunk → Entity. Creates HAS_FEATURE, HAS_SYMPTOM, HAS_SOLUTION via MERGE. |

**Decisions baked in:** No entity resolution/dedup (prompt consistency is sufficient). No RESOLVED_BY relationships. No relationship properties. No idempotency handling.

---

## 3. Expanded GraphRAG Retriever Examples

### What the lab currently demonstrates

The aircraft lab shows four retriever patterns: VectorRetriever (pure semantic search), VectorCypherRetriever (vector search plus Cypher enrichment), HybridRetriever (vector plus fulltext keyword search), and HybridCypherRetriever (hybrid plus Cypher). These operate within the document-chunk layer. The Cypher enrichment reaches into the structured graph but only through keyword matching (checking if chunk text CONTAINS system names).

### Proposed retriever examples for the retail assistant

Each example follows the same format: state the user question, show what plain vector search returns, show what entity-aware retrieval adds, and highlight the cross-document connections that only the entity layer makes possible.

**Example 1 — Entity-Aware Vector Retrieval: "My running shoes feel flat and unresponsive. What should I do?"**

A plain VectorRetriever finds the 3-5 chunks most semantically similar to the query. It likely returns chunks from the Nike Pegasus articles about React foam degradation — the closest semantic match. It misses the broader context.

An entity-aware VectorCypherRetriever starts with the same vector search but then traverses from the matched chunks through their extracted entities. It follows Chunk → REPORTS_SYMPTOM → Symptom ("cushion responsiveness loss") ← REPORTS_SYMPTOM ← Chunk (other chunks) to find that this same symptom is reported across Ultraboost, Nimbus, and Ghost 16 documents. It also follows Chunk → PROVIDES_SOLUTION → Solution ← PROVIDES_SOLUTION ← Chunk to find brand-specific solutions for each. The agent can now tell the customer: "This is normal midsole wear. All foam technologies degrade over 300-500 miles. Here's what to do for your specific shoe." No amount of vector similarity alone would reliably surface a Brooks Ghost review when the query matched a Nike Pegasus article.

**Example 2 — Cross-Document Entity Traversal: "Is the Continental outsole on the Ultraboost durable?"**

A VectorCypherRetriever with entity traversal finds all chunks that mention the Feature "Continental rubber outsole", regardless of which document type they come from. It pulls together: the knowledge article describing the warranty process (KA-008), the support ticket where a customer got a replacement (T-006), and the 1-star review complaining about peeling after 3 months (R-007). It also finds any enriched mentions from other products that share the same outsole issue. The agent synthesizes: "The Continental outsole has known separation issues reported by multiple customers. If your pair is within 6 months of purchase, Adidas offers warranty replacement. For minor separation, shoe adhesive provides a temporary fix."

**Example 3 — Symptom-First Retrieval (Graph-First, No Vector Search): "What are the most common problems with running shoes?"**

Instead of starting with vector search, this retriever starts with a pure graph query. It traverses from all Symptom nodes back through REPORTS_SYMPTOM to their Chunks, then through the source documents to their Products, filtering to products in the Running Shoes category. It counts how many documents report each symptom and ranks them. The result is a structured answer: "The top issues are (1) cushion degradation after 300+ miles, reported across all 5 running shoe brands, (2) outsole separation, reported for Ultraboost and Pegasus, (3) heel blistering, reported for Pegasus and Nimbus, (4) sizing runs narrow, reported for Pegasus and Ghost." No embedding is needed — the graph structure itself answers the question.

**Example 4 — Causal Chain Retrieval: "Will my Nike Pegasus outsole peel like my friend's Ultraboost did?"**

The retriever uses vector search to find chunks about outsole peeling, then traverses through the shared Symptom entity to check whether other products have the same issue. It follows Symptom ("outsole separation") ← REPORTS_SYMPTOM ← Chunk ← HAS_CHUNK ← (source document) → COVERS/ABOUT/REVIEWS → Product to find every product that has a document mentioning this symptom. If the enriched Pegasus data includes outsole separation mentions, the agent gives a grounded answer: "Yes, outsole separation has been reported for the Pegasus as well, though less frequently than for the Ultraboost. The Pegasus uses a different outsole compound, so the failure pattern may differ." If no Pegasus documents mention it, the agent can honestly say: "There are no reports of outsole separation for the Pegasus in our data."

**Example 5 — Solution Discovery via Feature Similarity: "How do I clean yellowed foam on my shoes?"**

The retriever finds chunks about yellowing through vector search, then traverses Chunk → REPORTS_SYMPTOM → Symptom ("yellowing / oxidation") ← REPORTS_SYMPTOM ← Chunk to find all chunks reporting this symptom. From those chunks it follows Chunk → PROVIDES_SOLUTION → Solution to find all known fixes, and traces back through the source documents to find which products each solution applies to. The result: "Yellowing affects both Ultraboost (Boost foam) and Air Max 90 (midsole and Air unit). The same cleaning method works for both: apply a paste of baking soda and hydrogen peroxide, scrub gently, and leave in indirect sunlight for 2-3 hours."

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

2. **A new loading script** (`load_graphrag.py`) — A 4-stage pipeline that chunks the existing documents, embeds the chunks, extracts Feature/Symptom/Solution entities using an LLM, and links entities to chunks and products. Runs after `load_products.py` and adds the semantic layer to the graph.

3. **Five retriever examples** — Progressive demonstrations from entity-aware vector search to pure graph-first retrieval, each showing what the entity layer adds that plain vector search cannot provide. Uses the same neo4j-graphrag retriever classes as the aircraft lab but with Cypher queries that traverse the entity layer.

The key technology highlight is LLM-powered entity extraction — the bridge between raw document text and a structured knowledge graph that agents can reason over.
