## Overview

This repository is a production-ready retail shopping assistant that runs on Databricks. It combines a Neo4j knowledge graph with Databricks lakehouse tables to answer product questions, remember customer preferences, and make personalized recommendations. The assistant is built as a LangGraph ReAct agent, wrapped in an MLflow ChatAgent, and deployed to a Databricks Model Serving endpoint. A separate Genie lakehouse agent handles analytics queries over Delta Lake tables, while this agent handles everything that benefits from graph structure: product search, support diagnostics, and cross-session memory.

## Key Technologies

- **Databricks Model Serving** — hosts the agent as a serverless endpoint with scale-to-zero support
- **MLflow (Models from Code)** — the agent is logged as a Python source file rather than a serialized object, which avoids issues with async resources and gives full control over startup
- **LangGraph** — provides the ReAct agent loop and tool runtime with dependency injection
- **Claude Sonnet 4.6 on Databricks** — the LLM powering the agent, accessed through the Databricks Foundation Model API
- **Neo4j** — stores the product knowledge graph (products, categories, brands, attributes, and their relationships) and the agent memory graph (conversation history, user preferences, reasoning traces). Three Neo4j libraries divide the work:
  - **neo4j Python driver** — async and sync drivers for direct Cypher execution, used for graph queries in the deployed agent and DDL operations during data loading
  - **neo4j-graphrag-python** — handles knowledge graph construction (chunking, embedding, entity extraction) and provides the retriever patterns (VectorCypher, HybridCypher, Text2Cypher) demonstrated in the retriever demo scripts
  - **neo4j-agent-memory** — gives the agent persistent short-term, long-term, and reasoning memory backed by Neo4j, with built-in entity extraction and semantic search over past interactions
  - **Neo4j Spark Connector** — two-way bridge between Databricks and Neo4j, used for bulk-loading product nodes and relationships from Spark DataFrames
- **Databricks Delta Lake** — stores transactional and analytical data (1M+ transactions, customers, reviews, inventory) queried by the Genie agent via natural language to SQL
- **Databricks BGE Embeddings** — a 1024-dimension embedding model used for vector similarity search across both product descriptions and knowledge articles

## Integration Patterns

- **Dual database architecture** — Neo4j handles relational and semantic queries (product graph, support knowledge, memory) while Delta Lake handles analytical queries (sales trends, inventory counts). The two stores share a product ID key so results can be joined across systems.
  - A Databricks supervisor agent routes each question to the right backend: Neo4j for product and support queries, Genie for analytics over Delta Lake
  - Neo4j stores 570+ products with Category, Brand, and Attribute nodes connected by relationships like BOUGHT_TOGETHER and SIMILAR_TO
  - Delta Lake holds 1M+ rows across five tables (transactions, customers, reviews, inventory, stores) with column comments so Genie can generate SQL from natural language
- **GraphRAG retrieval** — knowledge articles, support tickets, and reviews are chunked, embedded, and linked to product nodes in Neo4j. At query time, the agent runs a vector search to find relevant chunks, then traverses graph relationships to surface related products, known symptoms, and solutions. This gives better answers than vector search alone because it follows the structure of the data.
  - Source documents are split into chunks, embedded with Databricks BGE, and stored as Chunk nodes with vector and fulltext indexes
  - An LLM extracts Feature, Symptom, and Solution entities from each chunk and links them back into the graph
  - Three retrieval modes: vector search with entity traversal, hybrid (fulltext + vector) with traversal, and product-scoped symptom/solution lookup
- **Three-layer memory** — short-term memory (scoped to a session) stores the current conversation and extracted entities. Long-term memory (scoped to a user) stores preferences like favorite brands and budget ranges. Reasoning memory records past multi-step problem-solving approaches so the agent can reuse successful strategies.
  - Short-term: stores messages with automatic entity extraction (people, organizations, locations, objects) scoped to a session ID
  - Long-term: tracks brand, category, budget, activity, and material preferences scoped to a user ID and persisted across sessions
  - Reasoning: records multi-step problem-solving traces with per-step thoughts, tool calls, and outcomes so the agent can recall successful approaches for similar future tasks
- **Neo4j Agent Memory library on Databricks** — shows how to integrate the neo4j-agent-memory Python library into a Databricks Model Serving environment, from initialization through to per-request usage across all three memory layers.
  - The MemoryClient is initialized at startup with Neo4j credentials pulled from Databricks secrets and a custom DatabricksEmbedder that wraps the Foundation Model API to satisfy the library's Embedder interface
  - Each incoming request constructs a RetailContext with the shared MemoryClient plus the caller's session ID and user ID, and LangGraph injects that context into every tool automatically via ToolRuntime
  - Tools call the MemoryClient directly for short-term operations (store and recall messages), long-term operations (track and retrieve preferences with user ID metadata), and reasoning operations (record and search multi-step traces)
- **Persistent async event loop** — the Neo4j async driver must stay bound to one event loop. The serving adapter creates a background thread with a long-lived loop and dispatches all async work there, avoiding the problems that come with creating and destroying loops per request.
  - A daemon thread runs a single asyncio loop for the lifetime of the serving process
  - The MemoryClient connects on that loop at startup so the Neo4j driver is bound to it from the start
  - Every incoming request dispatches async work to the same loop via run_coroutine_threadsafe

## What This Teaches

- How to deploy a LangGraph agent to Databricks Model Serving using MLflow's Models from Code pattern
- How to use Neo4j as both a domain knowledge graph and an agent memory store in the same application
- How to combine vector search with graph traversal (GraphRAG) to get more relevant retrieval results than either approach alone
- How to build a multi-agent system where a supervisor routes questions to specialized agents (graph agent vs. SQL agent) based on what each is good at
- How to manage secrets, async resources, and multi-tenant state in a serverless serving environment
