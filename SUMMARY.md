## Overview

This repository is a production-ready retail shopping assistant that runs on Databricks. It combines a Neo4j knowledge graph with Databricks lakehouse tables to answer product questions, remember customer preferences, and make personalized recommendations. The assistant is built as a LangGraph ReAct agent, wrapped in an MLflow ChatAgent, and deployed to a Databricks Model Serving endpoint. A separate Genie lakehouse agent handles analytics queries over Delta Lake tables, while this agent handles everything that benefits from graph structure: product search, support diagnostics, and cross-session memory.

## Key Technologies

- **Databricks Model Serving** — hosts the agent as a serverless endpoint with scale-to-zero support
- **MLflow (Models from Code)** — the agent is logged as a Python source file rather than a serialized object, which avoids issues with async resources and gives full control over startup
- **LangGraph** — provides the ReAct agent loop and tool runtime with dependency injection
- **Claude Sonnet 4.6 on Databricks** — the LLM powering the agent, accessed through the Databricks Foundation Model API
- **Neo4j** — stores the product knowledge graph (products, categories, brands, attributes, and their relationships) and the agent memory graph (conversation history, user preferences, reasoning traces)
- **Databricks Delta Lake** — stores transactional and analytical data (1M+ transactions, customers, reviews, inventory) queried by the Genie agent via natural language to SQL
- **Databricks BGE Embeddings** — a 1024-dimension embedding model used for vector similarity search across both product descriptions and knowledge articles

## Integration Patterns

- **Dual database architecture** — Neo4j handles relational and semantic queries (product graph, support knowledge, memory) while Delta Lake handles analytical queries (sales trends, inventory counts). The two stores share a product ID key so results can be joined across systems.
- **GraphRAG retrieval** — knowledge articles, support tickets, and reviews are chunked, embedded, and linked to product nodes in Neo4j. At query time, the agent runs a vector search to find relevant chunks, then traverses graph relationships to surface related products, known symptoms, and solutions. This gives better answers than vector search alone because it follows the structure of the data.
- **Three-layer memory** — short-term memory (scoped to a session) stores the current conversation and extracted entities. Long-term memory (scoped to a user) stores preferences like favorite brands and budget ranges. Reasoning memory records past multi-step problem-solving approaches so the agent can reuse successful strategies.
- **ToolRuntime dependency injection** — every tool receives a typed context object (containing the Neo4j client, session ID, and user ID) at invocation time instead of relying on global state. This keeps the tools testable and supports multi-tenant serving from a single endpoint.
- **Persistent async event loop** — the Neo4j async driver must stay bound to one event loop. The serving adapter creates a background thread with a long-lived loop and dispatches all async work there, avoiding the problems that come with creating and destroying loops per request.

## What This Teaches

- How to deploy a LangGraph agent to Databricks Model Serving using MLflow's Models from Code pattern
- How to use Neo4j as both a domain knowledge graph and an agent memory store in the same application
- How to combine vector search with graph traversal (GraphRAG) to get more relevant retrieval results than either approach alone
- How to build a multi-agent system where a supervisor routes questions to specialized agents (graph agent vs. SQL agent) based on what each is good at
- How to manage secrets, async resources, and multi-tenant state in a serverless serving environment
