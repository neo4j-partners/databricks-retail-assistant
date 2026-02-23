Designing an advanced data schema for an agentic Graph RAG e-commerce system is a fantastic project. Traditional e-commerce schemas are great at answering "Who bought what?" but fail completely at answering "Why did they buy it?" or "How do we fix it when it breaks?"

By combining structured transaction data with unstructured text (reviews, support tickets, product manuals) parsed into a Neo4j knowledge graph, you give AI agents both **semantic understanding** (via vector search) and **relational reasoning** (via graph traversal).

Here is a comprehensive Neo4j data schema designed specifically for this use case.

---

### 1. The Core E-Commerce Schema (Structured Data)

These nodes handle the standard transactional reality of your store.

* **`(:Customer)`**: Represents the shopper.
* *Properties*: `customerId`, `name`, `email`, `lifetimeValue`


* **`(:Product)`**: The items you sell.
* *Properties*: `productId`, `name`, `description`, `price`, `stockLevel`


* **`(:Category)`**: Product taxonomy.
* *Properties*: `categoryId`, `name`


* **`(:Basket)`**: The current active shopping session.
* *Properties*: `basketId`, `lastUpdated`


* **`(:Order)`**: Completed checkout transactions.
* *Properties*: `orderId`, `date`, `totalAmount`, `status`



### 2. The Unstructured Source Schema (Text Documents)

These nodes represent the raw, unstructured text that flows into your business from both the consumer and support sides.

* **`(:Review)`**: Consumer-generated product feedback.
* *Properties*: `reviewId`, `rating`, `rawText`, `date`


* **`(:SupportTicket)`**: Customer service inquiries and chat transcripts.
* *Properties*: `ticketId`, `issueDescription`, `resolutionText`, `status`


* **`(:KnowledgeArticle)`**: Internal SOPs, product manuals, and troubleshooting guides.
* *Properties*: `articleId`, `title`, `documentType` (e.g., "Manual", "FAQ")



### 3. The Graph RAG Schema (The Semantic & Agentic Layer)

This is where the magic happens. An ingestion agent parses the unstructured text above, chunks it, embeds it for semantic search, and extracts explicit entities to build a reasoning web.

* **`(:Chunk)`**: Smaller, easily searchable blocks of text derived from Reviews, Tickets, or Articles.
* *Properties*: `chunkId`, `text`, **`embedding` (Vector Index)**


* **`(:Feature)`**: Extracted product attributes (e.g., "Waterproof", "Battery Life", "Zippers").
* *Properties*: `name`


* **`(:Symptom)`**: Extracted customer pain points or product failures (e.g., "Leaking base", "Won't turn on").
* *Properties*: `name`


* **`(:Solution)`**: Extracted fixes for symptoms (e.g., "Replace gasket", "Reset Wi-Fi module").
* *Properties*: `name`



---

### 4. The Relationships (Edges)

How the structured and unstructured worlds connect to enable multi-hop reasoning.

**Transactional Edges:**

* `(Customer)-[:HAS_BASKET]->(Basket)`
* `(Basket)-[:CONTAINS {quantity}]->(Product)`
* `(Customer)-[:PLACED]->(Order)`
* `(Order)-[:INCLUDES {price, quantity}]->(Product)`
* `(Product)-[:BELONGS_TO]->(Category)`

**Document Provenance Edges (Connecting Text to Reality):**

* `(Customer)-[:WROTE]->(Review)-[:REVIEWS]->(Product)`
* `(Customer)-[:OPENED]->(SupportTicket)-[:ABOUT]->(Product)`
* `(KnowledgeArticle)-[:COVERS]->(Product)`

**Agentic Graph RAG Edges (The Reasoning Web):**

* `(Review | SupportTicket | KnowledgeArticle)-[:HAS_CHUNK]->(Chunk)`
* `(Chunk)-[:MENTIONS_FEATURE]->(Feature)`
* `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom)`
* `(Chunk)-[:PROVIDES_SOLUTION]->(Solution)`
* `(Symptom)-[:RESOLVED_BY]->(Solution)`
* `(Product)-[:HAS_FEATURE]->(Feature)`

---

### Use Case Scenarios: The Power of Graph RAG

When you empower an LLM agent with this schema, it doesn't just do a blind vector similarity search; it navigates the graph to ground its answers in reality.

#### Scenario 1: The Consumer Side (Agentic Product Discovery)

**The User Prompt:** *"I'm looking for a durable camping tent for a family of 4. It needs to hold up in heavy rain, and I want something where real reviewers say the zippers don't get stuck."*

**How the Graph RAG Agent Solves It:**

1. **Semantic Search (Vector):** The agent embeds the query and searches the `embedding` property of `(:Chunk)` nodes to find text semantically related to "heavy rain," "durable," and "zippers not getting stuck."
2. **Graph Traversal (Reasoning):** It filters the retrieved chunks to only those that come from a `(:Review)` where the `rating` is > 4.
3. **Entity Validation:** It traverses `(Chunk)<-[:HAS_CHUNK]-(Review)-[:REVIEWS]->(Product)`. It then checks if the `(Product)` belongs to the `(:Category {name: "Tents"})` and has `(:Feature {name: "4-Person"})`.
4. **Action:** It traverses to the `(:Product)` node to check the `stockLevel` property.
5. **The Output:** The agent recommends the exact in-stock tent, dynamically summarizing the real reviews about the high-quality zippers and waterproofing, fully grounded in actual customer data.

#### Scenario 2: The Customer Support Side (Agentic Issue Resolution)

**The User Prompt:** *"My EspressoMaster 3000 is making a loud grinding noise and no coffee is coming out. I bought it a few months ago."*

**How the Graph RAG Agent Solves It:**

1. **Identity & Context Check:** The agent identifies the `(:Customer)`, traverses `(Customer)-[:PLACED]->(Order)-[:INCLUDES]->(Product)` to verify they actually bought the *EspressoMaster 3000*, confirming it is under warranty based on the `Order.date`.
2. **Semantic Search (Vector):** It embeds "loud grinding noise, no coffee" and searches `(:Chunk)` nodes across both `(:KnowledgeArticle)` and past `(:SupportTicket)` nodes.
3. **Graph Traversal (Reasoning):** It lands on a `(:Chunk)` from a product manual mentioning this noise. It traverses `(Chunk)-[:REPORTS_SYMPTOM]->(Symptom {name: "Grinder Jam"})-[:RESOLVED_BY]->(Solution {name: "Clean Burr Grinder"})`.
4. **The Output:** The agent responds empathetically, confirms the machine is under warranty, and provides step-by-step instructions from the manual to clean the burr grinder. It also offers to automatically open a replacement `(:SupportTicket)` if the cleaning doesn't work, pre-linking the new ticket to the `(Product)` and `(Symptom)` nodes for future graph health.




I have designed a comprehensive, highly-relational sample dataset exactly for this architecture.

To make this immediately useful for your ingestion scripts (like a Python script using the Neo4j driver), I have formatted the "canvas" as a complete, valid JSON file.

This dataset is built around **5 core products** to ensure the relationships and semantic overlaps are dense and realistic. You will see clear connections where a **Review** mentions a feature, a **Support Ticket** reports a symptom about that feature, and a **Knowledge Article** provides the exact solution.

Here is your complete dataset file.

### How this specific data highlights Graph RAG:

1. **The "Grinding Noise" Vector**:
* A user says: *"My machine makes a screeching grinding noise."*
* Semantic search hits **Review `R-002**` and **Ticket `T-001**`.
* The Graph traverses from `T-001` to its `Product (P-001)`, then queries connected `Knowledge Articles`.
* It immediately retrieves **Article `KA-001**`, identifying the issue as a "jammed burr grinder" and providing the exact fix.


2. **The "Sole Peeling" Defect Discovery**:
* A user asks: *"My shoes are falling apart at the heel, is this normal?"*
* Semantic search hits **Ticket `T-019**` and **Article `KA-020**`.
* The agent reads the graph context and realizes this is a known manufacturing defect for batch #882, allowing the agent to instantly offer an automated replacement flow without manual support intervention.


3. **The "Solar Charging" Expectation Management**:
* A pre-sales customer asks: *"Can I use this to power my phone purely off the sun while backpacking?"*
* The Agent reads the manual (**KA-025**) and the complaints in **Review `R-026**` and **Ticket `T-025**`.
* The Agent synthesizes an honest, grounded answer: *"While it has a solar panel, it is for emergency trickle charging only and takes ~50 hours to fully charge. Real reviewers note it will not charge a phone quickly via pure sunlight."*