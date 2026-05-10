# Agentic Commerce Demo: Framing and Wireframes

A framing document for designing a basic demo client on top of the deployed retail agent. This document covers the business use case, the background that motivates the demo, concrete demo ideas the project can support today, and ASCII wireframes for a Databricks App built with Streamlit or Dash.

For deeper architectural background on the GraphRAG and memory layer behind the agent, see [agentic-commerce.md](agentic-commerce.md). For implementation notes on the GraphRAG load, see [DevelopersGuideGraphRAG-Databricks.md](DevelopersGuideGraphRAG-Databricks.md).

---

## 1. Business Use Case

**Agentic commerce** is the shift from search-driven shopping to agent-driven shopping. Instead of a customer typing keywords into a search bar and scrolling a results grid, the customer expresses intent in natural language and an agent does the work: it interprets the request, traverses product relationships, retrieves grounded knowledge from manuals and reviews, recalls what the customer cares about, and returns a small set of decisions rather than a long list of links.

The demo we are framing here is a customer-facing storefront assistant. A shopper opens the app, asks a real question ("I need a wireless mouse that works well with my MacBook for long coding sessions"), and the agent responds with a short ranked answer, an explanation of why each product fits, and a panel showing the graph traversal and retrieval that produced the answer. The behind-the-scenes panel is the differentiator. Most retail chatbots are opaque. This demo shows the knowledge graph hops, the GraphRAG chunks, and the memory writes as they happen, so a viewer understands why agentic commerce is different from classic recommendation engines or vector-only RAG.

## 2. Business Background

Three forces are converging to make agentic commerce viable now.

**Customers expect conversational shopping.** Generative chat interfaces have trained users to expect a single answer, not ten blue links. Retailers that keep showing keyword grids will feel increasingly dated against assistants that can reason about fit, compatibility, and prior purchases.

**Catalogs have always been graphs, but most stacks treat them as rows.** A product is connected to a brand, a category, attributes, compatible accessories, frequently bought-together items, support articles, reviews, and the people who bought it. Relational stores can model this, but every interesting query becomes a multi-table join with no useful index. A graph database makes those traversals first-class, and an agent can use them as tools without writing SQL.

**RAG alone is not enough for commerce.** Vector search retrieves chunks that look similar to the query. It cannot answer "which accessories are compatible with the laptop this customer bought last quarter and are in stock at their nearest store." That question requires structure, memory, and retrieval working together. GraphRAG plus agent memory on a single graph gives the agent all three in one place.

This project provides the foundation for that shift. The product graph encodes catalog structure. The GraphRAG layer turns knowledge articles, support tickets, and reviews into queryable entities (features, symptoms, solutions). Agent memory captures session context and long-term preferences, so the agent personalizes without retraining. The deployed Model Serving endpoint exposes all of this as a single ChatAgent the demo client can call.

## 3. What the Project Provides for the Demo

The demo client gets the following capabilities for free from the deployed agent. These are the building blocks any demo concept can mix and match.

| Capability | Source tool group | What the UI can show |
|---|---|---|
| Natural language product search | Product tools | Ranked product cards |
| Product detail and related products | Product tools | "Often paired with" panel via `SIMILAR_TO` and `BOUGHT_TOGETHER` |
| GraphRAG knowledge answers | Knowledge tools | Cited chunks with source document |
| Product issue diagnosis | Knowledge tools | Symptom to solution path with source articles |
| Hybrid keyword and vector search | Knowledge tools | "Why this matched" with both signals |
| Session memory | Memory tools | A "what the agent remembers about this session" sidebar |
| Long-term preferences | Preference tools | A "what we know about you" profile chip |
| Preference-aware recommendations | Commerce tools | A second results lane reranked by user profile |
| Multi-step reasoning trace | Reasoning tools | A timeline of the agent's steps |

The endpoint is a single MLflow ChatAgent, so the demo client only needs to call one HTTP endpoint and render whatever the agent returns. The "behind-the-scenes" panel is the agent's tool-call history, not a separate API.

## 4. Demo Concepts

Six demo angles, ordered from the core concept the user proposed to broader stretches. Each one is feasible against the agent as it ships today.

### 4.1 Agentic Search with Intelligence Surge (the core demo)

A single search box. The customer types intent in plain English. The agent answers with two to four ranked products, a one-sentence reason for each, and an "intelligence surge" panel that reveals what happened behind the scenes: which graph nodes were traversed, which knowledge chunks were retrieved, and which preferences were applied. A "similar and like" lane appears below the primary answer, populated by traversing `SIMILAR_TO` and `BOUGHT_TOGETHER` from the top result.

The intelligence surge is the differentiator. It turns the demo from "another chatbot" into "look at the reasoning."

### 4.2 Compatibility and Issue Diagnosis

A customer reports a problem ("my wireless headphones keep disconnecting from my laptop"). The agent uses the GraphRAG layer to walk Symptom to Solution edges, returns a diagnosis with cited support articles, and offers compatible replacements when the diagnosis points at a hardware mismatch. This shows GraphRAG doing something a flat vector store cannot: structured troubleshooting backed by the product graph.

### 4.3 Personalized Storefront That Learns in One Session

The demo opens with an empty profile. As the customer asks two or three questions, the agent extracts preferences ("prefers ergonomic", "Mac household", "budget under $150") and writes them to long-term memory. The storefront re-renders with a "For You" rail that visibly updates after each interaction. The point is to show memory being written and immediately read, not memory as a static profile.

### 4.4 Comparative Reasoning Across Products

The customer asks "what is the difference between Product A and Product B for someone who travels a lot?" The agent retrieves features and reviews for both products from the GraphRAG layer, structures them into a comparison table, and highlights the differences that matter for the stated context. This exercises the hybrid retriever and the reasoning trace tool.

### 4.5 Conversational Bundle Builder

The customer says "I'm setting up a home office under $1500." The agent traverses `BOUGHT_TOGETHER` and category relationships to assemble a bundle, explains each pick, and lets the customer swap any item for an alternative. Each swap triggers a re-traversal so the bundle stays internally consistent (compatible accessories, similar style). This is the most "agentic" of the demos because the agent is making a plan, not just answering a question.

### 4.6 Behind-the-Glass Operator View

Same agent, different audience. Instead of a shopper UI, a merchandiser or support analyst sees the live conversation, the graph traversals, the memory writes, and the retrieval scores. They can replay a session, inspect why the agent picked a particular product, and flag bad answers for review. This demo doubles as the "trust" story for stakeholders who want to see governance, not just chat.

## 5. Wireframe Layouts

All wireframes assume a Databricks App built with Streamlit or Dash, which constrains us to a vertical-first layout with a sidebar and one or two main panels. Widths assume a typical 1200 to 1400 px viewport.

### 5.1 Wireframe A: Agentic Search (core demo, single page)

The hero layout for demo 4.1. A search bar sits at the top. The agent answer fills the main column. The intelligence surge lives in a right rail that can be collapsed.

```
+----------------------------------------------------------------------+
|  RetailAgent                            [ Profile: empty ] [ Reset ] |
+----------------------------------------------------------------------+
|                                                                      |
|  Ask anything about our catalog                                      |
|  +--------------------------------------------------------+ [ Ask ]  |
|  | wireless mouse for long coding sessions on a MacBook   |          |
|  +--------------------------------------------------------+          |
|                                                                      |
+----------------------------------------+-----------------------------+
|  ANSWER                                | INTELLIGENCE SURGE  [ - ]   |
|                                        |                             |
|  Top picks for you                     | Tools used                  |
|                                        |  1. product_search          |
|  +----------------------------------+  |  2. graphrag_knowledge      |
|  | [img]  Logitech MX Master 3S     |  |  3. related_products        |
|  |        $99 . 4.7 stars           |  |                             |
|  |  Why: ergonomic, low-latency BT, |  | Graph hops                  |
|  |  long battery, MacOS support     |  |  Product -> Brand           |
|  |                          [ Add ] |  |  Product -> Attribute       |
|  +----------------------------------+  |  Product -> SIMILAR_TO -> 3 |
|                                        |                             |
|  +----------------------------------+  | Knowledge chunks            |
|  | [img]  Keychron M3 Pro           |  |  - "MacOS Bluetooth tips"   |
|  |        $79 . 4.5 stars           |  |  - "Ergonomic mouse review" |
|  |  Why: lightweight, programmable  |  |                             |
|  |                          [ Add ] |  | Memory writes               |
|  +----------------------------------+  |  + pref: macos_user         |
|                                        |  + pref: ergonomic          |
|  Similar and frequently paired         |  + pref: budget_under_150   |
|  +-----+ +-----+ +-----+ +-----+       |                             |
|  | MX  | | M4  | | Pad | | Pad |       | Latency: 1.4s               |
|  +-----+ +-----+ +-----+ +-----+       |                             |
+----------------------------------------+-----------------------------+
```

### 5.2 Wireframe B: Conversational Layout with Persistent Memory Sidebar

For demos 4.3 and 4.5. Chat on the left, live profile and bundle state on the right. The right rail is the agent's memory and the running plan, both visibly updating.

```
+----------------------------------------------------------------------+
|  RetailAgent . Conversational Demo            [ New session ]        |
+----------------------------------------------------------------------+
|                                          |                           |
|  CONVERSATION                            | WHAT WE REMEMBER          |
|                                          |                           |
|  > I'm setting up a home office under    | Preferences (long term)   |
|    $1500                                 |  . Mac household          |
|                                          |  . Ergonomic preferred    |
|  Bot: Great. Are you mostly on video     |  . Budget: $1500          |
|  calls or focused work?                  |                           |
|                                          | Session facts             |
|  > Mostly focused work, some calls       |  . Use case: home office  |
|                                          |  . Mix: focus + calls     |
|  Bot: Here is a starter bundle:          |                           |
|   . Standing desk converter ($249)       | CURRENT BUNDLE            |
|   . Ergonomic chair ($499)               |  Total: $1297 / $1500     |
|   . MX Master 3S ($99)                   |                           |
|   . Keychron K8 ($129)                   |  [ x ] Standing desk      |
|   . 4K webcam ($179)                     |  [ x ] Ergonomic chair    |
|   . Boom mic ($142)                      |  [ x ] MX Master 3S       |
|                                          |  [ x ] Keychron K8        |
|  Want to swap any item?                  |  [ x ] 4K webcam          |
|                                          |  [ x ] Boom mic           |
|  +-----------------------------------+   |                           |
|  | Type a follow up...               |   |  [ Compatibility check ]  |
|  +-----------------------------------+   |                           |
+------------------------------------------+---------------------------+
```

### 5.3 Wireframe C: Issue Diagnosis with Cited Sources

For demo 4.2. The interface pivots to a "support" framing. The diagnosis path renders as a small node-and-edge diagram, and cited articles appear inline.

```
+----------------------------------------------------------------------+
|  RetailAgent . Support Mode                                          |
+----------------------------------------------------------------------+
|  Describe the problem                                                |
|  +----------------------------------------------------------------+  |
|  | My headphones keep disconnecting from my laptop during calls   |  |
|  +----------------------------------------------------------------+  |
|                                                          [ Diagnose ]|
+----------------------------------------------------------------------+
|  DIAGNOSIS                              | SOURCES                    |
|                                         |                            |
|  Symptom -> Likely cause -> Solution    | [1] KB-882: Bluetooth      |
|                                         |     interference on MacOS  |
|     [Disconnects]                       |     "Disable handoff if    |
|         |                               |      pairing is unstable." |
|         v                               |                            |
|     [BT interference]                   | [2] Ticket #4421:          |
|         |                               |     Same device, resolved  |
|         v                               |     by firmware update.    |
|     [Update firmware] -- [1][2][3]      |                            |
|                                         | [3] Review on Sony WH-1000:|
|  Confidence: high                       |     "Firmware 2.4 fixed    |
|                                         |      call dropouts."       |
|  Recommended action                     |                            |
|   1. Update firmware to 2.4 or later    |                            |
|   2. If still failing, see alternatives |                            |
|                                         |                            |
|  Compatible alternatives                |                            |
|  +-------+ +-------+ +-------+          |                            |
|  | WH-04 | | QC-45 | | AT-M5 |          |                            |
|  +-------+ +-------+ +-------+          |                            |
+-----------------------------------------+----------------------------+
```

### 5.4 Wireframe D: Comparison View

For demo 4.4. Two products side by side, with the agent's reasoning in a band underneath.

```
+----------------------------------------------------------------------+
|  Compare for: "frequent traveler, light packer"                      |
+----------------------------------------------------------------------+
|  PRODUCT A                          |  PRODUCT B                     |
|  Sony WH-1000XM5                    |  Bose QC Ultra                 |
|  $349                               |  $429                          |
|                                     |                                |
|  [ image ]                          |  [ image ]                     |
|                                     |                                |
|  Weight        250g                 |  Weight        254g            |
|  Battery       30h                  |  Battery       24h             |
|  Foldable      no                   |  Foldable      yes             |
|  Case size     large                |  Case size     compact         |
|  ANC           class-leading        |  ANC           excellent       |
|                                     |                                |
|  Top review themes                  |  Top review themes             |
|  . battery champ                    |  . most comfortable            |
|  . awkward case for travel          |  . case fits in jacket pocket  |
+----------------------------------------------------------------------+
|  AGENT REASONING                                                     |
|  For a frequent traveler who packs light, case size and foldability  |
|  outweigh raw battery life. Product B wins on portability. Product A |
|  wins if battery is the priority and the bag has room.               |
|                                                                      |
|  Sources: 14 reviews, 2 KB articles, spec graph                      |
|  Recommendation: Product B               [ Add to cart ]             |
+----------------------------------------------------------------------+
```

### 5.5 Wireframe E: Operator / Behind-the-Glass View

For demo 4.6. A merchandiser or support lead sees the customer-facing answer on the left and the full instrumentation on the right. Useful as a "trust and governance" demo.

```
+----------------------------------------------------------------------+
|  Operator Console . Session #a93f-2210                  [ Live ]     |
+----------------------------------------------------------------------+
|  CUSTOMER VIEW                       | TRACE                         |
|                                      |                               |
|  > I want a gift for a runner        |  10:02:11 product_search      |
|                                      |   query: "gift runner"        |
|  Bot: A few options under $100:      |   results: 12                 |
|   . GPS watch . $89                  |                               |
|   . Wireless earbuds . $79           |  10:02:12 graphrag_knowledge  |
|   . Hydration vest . $65             |   matched chunks: 4           |
|                                      |   top score: 0.81             |
|  > she already has a watch           |                               |
|                                      |  10:02:18 preference_write    |
|  Bot: Got it. Refined picks:         |   key: "gift_for"             |
|   . Wireless earbuds . $79           |   value: "runner"             |
|   . Hydration vest . $65             |                               |
|   . Reflective jacket . $95          |  10:02:18 product_search      |
|                                      |   filter: -category:watch     |
|                                      |                               |
|                                      | MEMORY DELTA                  |
|                                      |  + recipient: runner          |
|                                      |  + exclude: watches           |
|                                      |                               |
|                                      | TOOL ERRORS: none             |
|                                      | TOTAL TOKENS: 4,210           |
|                                      |                               |
|  [ Flag answer ] [ Replay ]          | [ Export trace ]              |
+--------------------------------------+-------------------------------+
```

## 6. Recommended Starting Point

The simplest path to a compelling demo is to build Wireframe A first as a single-page Streamlit app, with a search box, an answer column, and a collapsible intelligence surge panel. The agent endpoint already returns tool-call history, so the surge panel is mostly rendering, not new backend work. From there, Wireframe B is a small extension (turn the search box into a chat input and add a memory sidebar), and Wireframe C reuses the same components with a different system prompt and a small node diagram.

If the goal is one demo that tells the whole story, build A. If the goal is a tour, build A then B then C.
