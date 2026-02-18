# Databricks Retail Assistant

A retail shopping assistant powered by LangGraph and Neo4j Agent Memory. It provides product search, personalized recommendations, inventory checking, and conversational memory through a FastAPI backend with SSE streaming.

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.13+ will be managed automatically)
- A running Neo4j instance (local or [Aura](https://neo4j.com/cloud/aura/))
- An OpenAI or Azure OpenAI API key

### 1. Install dependencies

This project depends on `neo4j-agent-memory` which is installed from a local checkout. Clone it first, then install both:

```bash
# Clone the agent-memory library (sibling directory)
git clone -b maf https://github.com/neo4j-labs/agent-memory.git ../agent-memory

# Install project dependencies
uv sync

# Install the local agent-memory checkout into the project venv
uv pip install -e "../agent-memory[openai,langchain]"
```

### 2. Configure environment

Copy the sample env file and fill in your values:

```bash
cp .env.sample .env
```

Edit `.env` with your Neo4j credentials and LLM API keys. See `.env.sample` for all available options.

### 3. Load sample product data

```bash
uv run python -m backend.scripts.load_products
```

### 4. Start the server

```bash
uv run python -m backend.main
```

The API will be available at `http://localhost:8000`.

### 5. Verify it works

```bash
uv run python -m backend.scripts.test_api
```

## Agent Memory

Most AI chatbots forget everything the moment a conversation ends. This assistant is different — it uses [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory) to give the agent persistent, structured memory backed by a Neo4j graph. Every conversation, preference, and learned fact is stored as nodes and relationships in the same Neo4j instance that holds the product catalog. Because memories are also embedded as vectors, the agent can semantically search its own past — finding relevant context even when the wording is completely different from the original conversation.

### Three layers of memory

The memory system organizes what the agent knows into three distinct layers:

**Short-term memory** keeps track of the current conversation. It stores each message exchanged between the user and the assistant within a session, so the agent can refer back to what was just said. When a session ends, this layer can be cleared without affecting anything else.

**Long-term memory** captures durable knowledge that persists across sessions. This includes entities the agent has learned about (people, products, locations, organizations, and events), user preferences (like "I prefer trail running shoes" or "I'm looking for gifts under $50"), and facts with temporal context. Entities are classified using a POLE+O model (Person, Object, Location, Event, Organization), which maps naturally to Neo4j node labels for efficient querying.

**Reasoning memory** records how the agent solved past problems. Each reasoning trace captures the steps taken, tools called, and outcomes reached during a task. When the agent encounters a similar request later, it can look up how it handled comparable situations before, leading to faster and more consistent responses.

### How the assistant uses memory

When a conversation starts, the assistant loads relevant context from all three memory layers — recent chat history, known entities and preferences, and similar past reasoning traces. This assembled context is passed to the LLM alongside the user's message, so the agent has a rich understanding of who it's talking to and what they've discussed before.

During a conversation, the agent also has access to a `search_memory` tool that it can call at any time. If a user asks something like "what did I say I was training for?", the agent can search across past messages, stored preferences, and entity records to find the answer.

The memory state is also accessible through API endpoints (`/memory/context`, `/memory/graph`, `/memory/preferences`) for debugging and visualization. You can verify the memory subsystem is working correctly by running:

```bash
uv run python -m backend.scripts.verify_memory
```

## Lakehouse Data Generation

Generate synthetic retail transaction data for Databricks Delta Lake integration. This produces CSV files that can be uploaded to a Databricks Unity Catalog Volume and converted to Delta Lake tables.

### Generate transaction data

Using the original 16-product catalog:

```bash
uv run python -m backend.scripts.generate_transactions
```

Using the expanded 570-product catalog (recommended):

```bash
uv run python -m backend.scripts.generate_transactions --expanded
```

This outputs CSVs to `data/lakehouse/`:

| File | Rows | Description |
|------|------|-------------|
| `transactions.csv` | ~1.15M | Line items across 500K orders |
| `customers.csv` | 5,000 | Customer dimension with segments |
| `reviews.csv` | ~115K | Product reviews linked to transactions |
| `inventory_snapshots.csv` | ~417K | Daily stock levels per product |
| `stores.csv` | 20 | Physical store locations |

### Verify the generated data

After generation, verify the CSVs with row counts, schema validation, and foreign key checks:

```bash
uv run python -m backend.scripts.generate_transactions --expanded --verify
```

This checks all CSV files exist, validates a sample of rows against Pydantic schemas, and confirms every product ID in transactions exists in the catalog. Exits with code 0 on success, 1 on failure.

### Upload to Databricks

The lakehouse setup script uses the [Databricks SDK](https://docs.databricks.com/en/dev-tools/sdk-python.html) with CLI profile authentication. The script will auto-create the Unity Catalog catalog, schema, and volume if they don't already exist, but the workspace and SQL warehouse must be set up beforehand.

#### Prerequisites

1. **Databricks workspace** with Unity Catalog enabled.
2. **Databricks CLI** installed (`pip install databricks-cli` or `brew install databricks`).
3. **A personal access token** — generate one from your workspace under **Settings > Developer > Access tokens**.
4. **A SQL Warehouse** — the script needs a running warehouse to execute SQL. Create one in your workspace:
   - Go to **SQL Warehouses** in the left sidebar
   - Click **Create SQL Warehouse**
   - Choose **Serverless** (recommended) or **Pro**
   - Name it (e.g., `retail_warehouse`) and start it
   - The warehouse must be in a **Running** state when you run the script
5. **Unity Catalog resources** — create the catalog, schema, and volume manually before running the script:
   - Go to **Catalog** in the left sidebar
   - Click **Create Catalog**, name it `retail_assistant`
   - Inside the catalog, create a schema named `retail`
   - Inside the schema, create a volume named `retail_volume`

#### 1. Configure a Databricks CLI profile

```bash
databricks configure --profile my-profile
```

Enter your workspace host (e.g., `https://adb-1234567890.12.azuredatabricks.net`) and personal access token when prompted. This saves credentials to `~/.databrickscfg`.

#### 2. Set environment variables

Add these to your `.env` (see `.env.sample`):

```env
DATABRICKS_PROFILE=my-profile
DATABRICKS_WAREHOUSE=retail_warehouse

# Optional (defaults shown)
# DATABRICKS_CATALOG=retail_assistant
# DATABRICKS_SCHEMA=retail
# DATABRICKS_VOLUME=retail_volume
```

#### 3. Run the table setup script

```bash
uv run python -m backend.scripts.lakehouse_tables
```

The script will:
1. Upload CSVs to the Unity Catalog Volume
2. Create Delta Lake tables with proper column types
3. Add table and column comments for Genie compatibility

Options:

```bash
# Skip upload (if CSVs are already in the volume)
uv run python -m backend.scripts.lakehouse_tables --skip-upload

# Skip table creation (upload only)
uv run python -m backend.scripts.lakehouse_tables --skip-tables
```

## Project Structure

```
backend/
├── main.py              # Entry point (uvicorn runner)
├── app.py               # FastAPI app factory and lifespan
├── config.py            # Pydantic settings from .env
├── constants.py         # Shared constants
├── dependencies.py      # FastAPI dependency injection
├── models/              # Pydantic request/response models
│   ├── chat.py
│   ├── health.py
│   ├── memory.py
│   ├── products.py
│   └── session.py
├── routes/              # API route handlers
│   ├── chat.py          # POST /chat, /chat/sync
│   ├── health.py        # GET /health
│   ├── memory.py        # GET /memory/*
│   └── products.py      # GET /products/*
├── tools/               # LangGraph agent tools
│   ├── cart.py
│   ├── inventory.py
│   ├── memory_tools.py
│   ├── product_search.py
│   └── recommendations.py
└── scripts/
    ├── product_catalog.py        # Product data constants (shared)
    ├── load_products.py          # Seed Neo4j with sample catalog
    ├── generate_transactions.py  # Generate lakehouse CSV data
    ├── lakehouse_tables.py       # Upload CSVs & create Delta Lake tables
    ├── test_api.py               # Integration test suite
    └── verify_memory.py          # Memory subsystem check
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Chat with SSE streaming |
| `POST` | `/chat/sync` | Chat (single response) |
| `GET` | `/memory/context` | Retrieve memory context for a session |
| `GET` | `/memory/graph` | Get knowledge graph for a session |
| `GET` | `/memory/preferences` | Get learned preferences |
| `GET` | `/products/search` | Search products by query |
| `GET` | `/products/{id}` | Get product details |
| `GET` | `/products/{id}/related` | Get related products |
