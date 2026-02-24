# Proposal: Expanding the Neo4j Lab with Entity Extraction, Unstructured Data Loading, and Advanced GraphRAG Retrievers

## Context

The current `databricks-neo4j-lab` workshop teaches participants how to build a dual-database AI agent architecture using an Aircraft Digital Twin dataset. It loads structured data (aircraft, systems, components, sensors, flights, maintenance events) into Neo4j, then demonstrates semantic search over a single maintenance manual using vector embeddings and several retriever patterns.

The workshop is effective at showing the mechanics of chunking, embedding, and retrieval. However, it stops short of demonstrating the full power of GraphRAG because it never extracts entities from unstructured text and never connects those entities back into the knowledge graph. The retrievers rely on keyword pattern-matching against chunk text (e.g., checking if a chunk `CONTAINS 'Engine'`) rather than traversing explicit entity relationships that were discovered during ingestion.

This proposal describes how to expand the lab to close that gap. The retail assistant project's sample dataset — with its product reviews, support tickets, and knowledge articles — provides a concrete model for what richer unstructured data looks like and how entity extraction transforms it into a reasoning graph.

---

## 1. Expanding the Sample Data to Support Entity Extraction

### What exists today

The aircraft lab has one piece of unstructured text: a single A320-200 maintenance manual. It gets chunked and embedded, but no entities are extracted from it. The chunks float in the graph connected only to a Document node and to each other via NEXT_CHUNK.

### What should change

The sample dataset needs multiple types of unstructured documents that contain overlapping entities, so that entity extraction can demonstrate cross-document connections. This is what makes GraphRAG valuable — an entity mentioned in a maintenance report can be linked to the same entity mentioned in a troubleshooting guide, a parts bulletin, and an incident narrative.

### Proposed new unstructured documents

**Maintenance Reports (per aircraft, per event):** Narrative text written by maintenance technicians describing what they found and what they did. These are richer than the current MaintenanceEvent nodes, which only have structured fields like fault code and severity. A maintenance report might say: "Replaced the fan blade assembly on the left V2500-A1 engine after detecting metal shavings in the oil filter during routine inspection. Torque values verified per AMM 72-00-00. Aircraft returned to service after engine ground run showed normal EGT and vibration readings."

**Airworthiness Directives and Service Bulletins:** Official documents that reference specific aircraft models, engine types, component part numbers, and failure modes. These are dense with extractable entities and create natural connections between documents and the existing aircraft topology.

**Pilot Reports (PIREPs):** Short narrative entries from flight crews reporting in-flight anomalies. A PIREP might say: "Intermittent EICAS message for ENG 2 oil pressure during climb. Oil quantity normal on post-flight check." These overlap with maintenance events and sensor readings.

**Incident and Delay Narratives:** Expanded text versions of the existing Delay nodes, providing the story behind a delay rather than just a cause code and duration.

### How the data should be structured for entity extraction

Each document should be written so that it naturally contains references to entities that already exist in the structured graph (specific aircraft tail numbers, system names, component types, sensor IDs) as well as entities that should be discovered and created during extraction (specific failure modes, part numbers, procedures, specifications, and causal relationships).

For example, a maintenance report that mentions "N95040A", "V2500-A1 Engine 1", "fan blade assembly", "metal shavings in oil filter", and "AMM 72-00-00" contains five extractable entities that each connect to different parts of the existing graph or create new nodes in the semantic layer.

The key principle: **entity extraction is only compelling when the same entity appears across multiple documents from different sources.** A fault mode mentioned in a maintenance report, a service bulletin, and a pilot report creates a three-way connection that no single document search could surface.

---

## 2. A Second Data Load Step: Unstructured Data Ingestion Pipeline

### Current loading architecture

The lab currently has two loading notebooks:
- **Notebook 01** loads the core aircraft topology (Aircraft, System, Component) using the Neo4j Spark Connector for bulk operations.
- **Notebook 02** loads the full operational dataset (Sensors, Flights, Delays, MaintenanceEvents, Removals) using the Neo4j Python driver.

A third notebook (Notebook 03 in Lab 7) loads the maintenance manual, chunks it, embeds it, and stores the chunks. But it does not extract entities or connect chunks to the existing graph through entity relationships.

### Proposed new notebook: Unstructured Data Ingestion with Entity Extraction

This should be a new notebook (or a significant expansion of Notebook 03) that demonstrates a complete unstructured data ingestion pipeline with the following stages:

**Stage 1 — Document Loading and Chunking.** Load each unstructured document (maintenance reports, service bulletins, PIREPs, delay narratives) from the Unity Catalog Volume. Chunk each document using the existing FixedSizeSplitter. Create Document and Chunk nodes with FROM_DOCUMENT and NEXT_CHUNK relationships. This part is already demonstrated and can be reused.

**Stage 2 — Embedding Generation.** Generate vector embeddings for each chunk using the Databricks Foundation Model API (databricks-bge-large-en). Store embeddings on Chunk nodes. Create vector and fulltext indexes. This part is also already demonstrated.

**Stage 3 — Entity Extraction (new).** Use a Databricks-hosted LLM (such as Meta Llama 3.3 70B via the Foundation Model API) to extract structured entities from each chunk. The LLM should be prompted to identify:
- **Components and Parts:** Specific parts mentioned (fan blade, oil filter, gasket, compressor stage 3)
- **Failure Modes / Symptoms:** What went wrong (metal shavings, oil pressure drop, EGT exceedance)
- **Procedures / Solutions:** What was done or should be done (replace gasket, torque per AMM 72-00-00, reset avionics module)
- **Specifications:** Operating limits, part numbers, document references (AMM 72-00-00, max EGT 950°C)
- **Aircraft References:** Tail numbers, models, and systems mentioned in the text

Each extraction creates new nodes (Symptom, Solution, Specification, FailureMode) or resolves to existing nodes in the structured graph (Aircraft, System, Component).

**Stage 4 — Entity Linking (new).** Connect extracted entities to chunks via explicit relationships:
- `(Chunk)-[:MENTIONS_COMPONENT]->(Component)`
- `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom)`
- `(Chunk)-[:PROVIDES_SOLUTION]->(Solution)`
- `(Chunk)-[:REFERENCES_SPEC]->(Specification)`
- `(Symptom)-[:RESOLVED_BY]->(Solution)`
- `(Component)-[:HAS_KNOWN_ISSUE]->(Symptom)`

Also connect extracted entities to the existing structured graph:
- `(Symptom)-[:AFFECTS]->(System)`
- `(Solution)-[:APPLIES_TO]->(Component)`

**Stage 5 — Entity Resolution (new).** Demonstrate basic entity deduplication. The same component might be referred to as "V2500-A1", "V2500", "left engine", or "Engine 1" across different documents. The pipeline should show how to normalize these references so that graph traversals work correctly across documents.

### Why this matters for the workshop

This second loading step transforms the graph from a document store with vector search into a true knowledge graph where unstructured text is woven into the structured topology. Participants see how raw text becomes actionable graph structure, which is the core value proposition of GraphRAG over plain RAG.

---

## 3. Expanded GraphRAG Retriever Examples

### What exists today

The lab currently demonstrates four retriever patterns:
1. **VectorRetriever** — Pure semantic similarity search over chunk embeddings
2. **VectorCypherRetriever** — Vector search followed by a hand-written Cypher query that enriches results with document metadata, adjacent chunks, or keyword-matched system connections
3. **HybridRetriever** — Combined vector and fulltext keyword search
4. **HybridCypherRetriever** — Hybrid search with Cypher enrichment

These are solid foundations, but they all operate within the document-chunk layer. The Cypher enrichment in VectorCypherRetriever does reach into the structured graph, but only through brittle keyword matching (checking if chunk text CONTAINS system names). None of the retrievers traverse the entity extraction layer because it does not exist yet.

### Proposed new retriever examples

Once entity extraction is in place, the lab should demonstrate these additional retrieval patterns:

**Entity-Aware Vector Retrieval.** Start with a vector search to find relevant chunks, then traverse from those chunks through extracted entity relationships to discover related information that vector similarity alone would miss. For example: a query about "engine vibration" finds a chunk from a maintenance report. The retriever then traverses `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom {name: "High Vibration"})-[:RESOLVED_BY]->(Solution)` to find the recommended fix, and `(Symptom)-[:AFFECTS]->(System)<-[:HAS_SYSTEM]-(Aircraft)` to find which aircraft in the fleet have experienced this issue.

**Cross-Document Entity Traversal.** Given a query about a specific component failure, retrieve chunks from multiple document types (maintenance reports, service bulletins, pilot reports) that all mention the same extracted entity. This demonstrates how entity extraction creates bridges between documents that have no direct relationship to each other. A maintenance report chunk and a service bulletin chunk might never appear together in a vector similarity search, but they both link to the same Symptom or Component node.

**Graph-First Retrieval (Reverse Direction).** Instead of starting with vector search and enriching with graph traversal, start with a structured graph query and then pull in relevant unstructured context. For example: "Show me all aircraft with critical maintenance events on hydraulic systems" starts as a pure Cypher traversal through Aircraft → System → MaintenanceEvent. Then for each result, traverse to related chunks via the entity layer to pull in the narrative context — the maintenance report describing what happened, the knowledge article with the troubleshooting procedure, the service bulletin with the long-term fix.

**Causal Chain Retrieval.** Traverse multi-hop paths through the entity layer to answer "why" questions. For example: "Why was flight UA-1234 delayed?" traverses Flight → Delay → (narrative chunk) → extracted Symptom → Component → MaintenanceEvent → (maintenance report chunk) → extracted Solution. This chain connects a flight delay to its root cause and resolution through a path that spans both structured and unstructured data.

**Comparative Retrieval.** Given a symptom or failure mode, retrieve and compare information across the fleet. Which aircraft models experience this issue? How was it resolved in each case? Were the resolutions different? This pattern traverses `(Symptom)<-[:REPORTS_SYMPTOM]-(Chunk)-[:FROM_DOCUMENT]->(Document)` across multiple documents and then groups results by aircraft model or system type.

**Community Summary Retrieval.** Use graph community detection algorithms (available in the Neo4j Graph Data Science library) to identify clusters of related entities — for example, a cluster of symptoms, components, and solutions that frequently co-occur. Pre-compute summaries of these communities and use them as an additional retrieval layer. When a query matches a community summary, return the summary along with the most relevant individual chunks from that community.

### How these examples should be structured

Each retriever example should follow the same pattern used in the existing notebooks:
1. State the question a user might ask
2. Explain which retrieval strategy is appropriate and why
3. Show the retriever configuration and Cypher traversal pattern
4. Compare the result to what a simpler retriever would return
5. Highlight what information was only accessible because of entity extraction and graph traversal

---

## 4. Key Technologies to Highlight

### Technologies already featured that should remain prominent

- **Neo4j Aura** as the graph database for both structured topology and the GraphRAG semantic layer
- **Databricks Unity Catalog** as the data governance and storage layer
- **Databricks Foundation Model APIs** for embeddings (BGE-large) and LLM inference (Llama 3.3 70B)
- **Neo4j Spark Connector** for high-throughput bulk loading from Databricks to Neo4j
- **AI/BI Genie Spaces** for natural language querying of time-series sensor data in the lakehouse
- **Databricks AgentBricks** for multi-agent supervisor orchestration
- **Neo4j MCP (Model Context Protocol)** for tool-based graph querying from agents

### New technologies that should be highlighted

**Neo4j Graph Data Science (GDS) Library.** The GDS library provides graph algorithms that are essential for advanced GraphRAG. Community detection algorithms (Louvain, Leiden) can identify clusters of related entities for community summary retrieval. Centrality algorithms (PageRank, betweenness) can identify the most important entities in the graph — the symptoms that connect to the most solutions, the components that appear in the most maintenance reports. Similarity algorithms can find structurally similar subgraphs. The lab should show how GDS runs natively inside Neo4j and how its results feed into the retrieval pipeline.

**LLM-Powered Entity Extraction Pipeline.** The entity extraction step is itself a significant technology demonstration. It shows how to use a Databricks-hosted LLM as a structured data extraction tool — prompting it with chunk text and a schema, receiving back structured JSON with entity types and relationships. This is a pattern that participants will reuse across many domains beyond aircraft maintenance.

**Neo4j Vector Index and Fulltext Index (Combined).** While these are already used, the expanded examples should more explicitly highlight how Neo4j's native vector index eliminates the need for a separate vector database. The graph database serves as both the vector store and the knowledge graph, which is a key architectural simplification.

**Databricks Workflows / Jobs.** The unstructured data ingestion pipeline (chunking, embedding, extraction, linking) is a natural fit for a Databricks Workflow that could run on a schedule as new documents arrive. While the lab uses notebooks for interactive exploration, pointing out how this pipeline would be operationalized via Workflows connects the workshop to production deployment patterns.

**Delta Lake Change Data Feed.** For the operational story, highlight how new documents arriving in the lakehouse (maintenance reports filed daily, pilot reports after each flight) can trigger incremental updates to the knowledge graph through Delta Lake's Change Data Feed. This connects the batch-loading workshop pattern to a real-time production architecture.

**Retrieval Quality Evaluation.** The lab should demonstrate how to measure whether GraphRAG retrieval is actually better than plain vector search. Databricks MLflow provides experiment tracking that can compare retrieval strategies across a set of test queries, measuring relevance, completeness, and grounding. This turns the retriever comparison from a qualitative demonstration into a quantifiable evaluation.

---

## Summary

The core expansion is straightforward: add richer unstructured documents to the sample data, build an entity extraction pipeline that connects text to the knowledge graph, and then show retriever patterns that traverse those entity connections. This transforms the workshop from "semantic search with some graph context" into a genuine GraphRAG demonstration where the graph is not just a container for chunks but an active reasoning structure that agents traverse to answer complex questions.

The retail assistant project's schema (with its Reviews, SupportTickets, KnowledgeArticles, Features, Symptoms, and Solutions) provides the conceptual blueprint. The aircraft maintenance domain provides equally rich opportunities: maintenance reports contain symptoms and solutions, service bulletins reference components and procedures, and pilot reports connect in-flight observations to ground-level maintenance actions. The entity extraction pipeline is the bridge between these raw documents and the structured knowledge graph.
