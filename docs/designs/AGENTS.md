# Multi-Agent Retail Assistant on Databricks

## Problem Statement

The project has a LangGraph ReAct agent with 14 LangChain tools (product search, recommendations, cart, inventory, memory) backed by a Neo4j knowledge graph. Meanwhile, the lakehouse holds 500K+ orders and 1.15M line items in Delta tables that are completely disconnected from the assistant.

This creates two problems:

1. **The graph agent has no access to transactional analytics** — it can traverse product relationships and preferences but cannot answer "what were our top-selling products last quarter?" or "which customers have the highest lifetime value?"
2. **The lakehouse data has no conversational interface** — the Delta tables sit idle unless someone writes SQL manually.

A multi-agent architecture solves both by giving each data source its own specialized agent and coordinating them through a supervisor.

## Proposed Solution

Deploy a **two-agent supervisor system** on Databricks using the Mosaic AI Agent Framework:

| Agent | Data Source | Capability |
|-------|------------|------------|
| **Neo4j KG Agent** | Neo4j Aura | Product search, recommendations, cart, inventory, memory — the existing 14 tools |
| **Genie Lakehouse Agent** | Unity Catalog Delta tables | Natural language SQL over transactions, customers, revenue, product performance |
| **Supervisor** | Routes between agents | Determines which agent (or both) should handle a query, synthesizes combined responses |

The supervisor is a [Databricks Supervisor Agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-systems) (AgentBricks) that combines both sub-agents into a single system. It uses advanced routing techniques to classify user intent, delegate to the appropriate sub-agent(s), and synthesize a unified response — no custom orchestration code required. The supervisor is configured through the Databricks UI and deployed as a Model Serving endpoint.

### Expected Outcomes

- Users ask questions in natural language and get answers that span both the knowledge graph and the lakehouse
- "Find me running shoes under $100 with good reviews" routes to the Neo4j KG Agent
- "What was the revenue trend for running shoes last quarter?" routes to the Genie Agent
- "Recommend products that are trending and match my preferences" hits both agents
- The system deploys as a single Databricks endpoint with automatic scaling, tracing, and a Review App for feedback

---

## Architecture

```
                         User
                          |
                   +--------------+
                   |  Supervisor  |
                   | (AgentBricks)|
                   +------+-------+
                          |
              +-----------+-----------+
              |                       |
     +--------v--------+    +--------v--------+
     | Neo4j KG Agent  |    | Genie Lakehouse |
     | (Tool-calling)  |    |     Agent        |
     +--------+--------+    +--------+--------+
              |                       |
     +--------v--------+    +--------v--------+
     |   Neo4j Aura    |    | Unity Catalog   |
     |  Knowledge Graph |    | Delta Tables    |
     +-----------------+    +-----------------+
```

### Component Breakdown

**Supervisor** — A Databricks Supervisor Agent (AgentBricks) configured through the workspace UI. The supervisor reads agent descriptions and the user query, then decides which agent(s) to invoke. If both agents return results, the supervisor synthesizes a combined answer. No custom routing code is needed — AgentBricks handles intent classification and orchestration automatically.

**Neo4j KG Agent** — A tool-calling ReAct agent with access to the existing 14 tools. Registered as a Unity Catalog function (or wrapped as a serving endpoint) so the supervisor can invoke it. Connects to Neo4j Aura over the network.

**Genie Lakehouse Agent** — A `GenieAgent` from `databricks-langchain` pointed at a Genie Space configured over the retail lakehouse tables. Translates natural language to SQL, executes it on a SQL warehouse, and returns results.

---

## Requirements

### R1: Genie Space Setup

Create a Genie Space in the Databricks workspace connected to the retail lakehouse tables in Unity Catalog:

- `retail.default.transactions` — 500K orders with order_id, customer_id, order_date, total, status
- `retail.default.transaction_items` — 1.15M line items with product_id, quantity, unit_price, discount
- `retail.default.products` — 570 products with name, category, brand, price, description
- `retail.default.customers` — customer profiles with signup_date, segment, lifetime_value

The Genie Space must include:
- Table and column descriptions so Genie generates accurate SQL
- Example SQL queries for common retail analytics (revenue by period, top products, customer cohorts, basket analysis)
- Synonyms for business terms (e.g., "sales" = revenue, "items sold" = quantity)
- Instructions scoping Genie to read-only retail analytics

### R2: Neo4j KG Agent — Modular, Portable Tools via `ToolRuntime`

Refactor the existing tools layer to be environment-agnostic using LangGraph's `ToolRuntime` dependency injection pattern, then build the agent on top:

- **Use `ToolRuntime[RetailContext]` for dependency injection** — tools declare a `runtime: ToolRuntime[RetailContext]` parameter that LangGraph injects automatically. The same tool objects run in any environment; only the context differs at invocation time.
- **Define a `RetailContext` dataclass** holding all external dependencies (`MemoryClient`, embedder, session info). This replaces the implicit closure with an explicit, typed contract.
- **Use `create_react_agent` with `context_schema=RetailContext`** — LangGraph wires the context into every tool call automatically.
- Use `ChatDatabricks` as the LLM (Llama 3.3 70B or DBRX) instead of OpenAI
- Package the Neo4j connection credentials as Databricks secrets
- A thin `ChatAgent` adapter wraps the LangGraph agent for Databricks Model Serving I/O compatibility — it is a 5-line shim, not the architecture

### R3: Multi-Agent Supervisor

Create a Databricks Supervisor Agent (AgentBricks) that coordinates the two agents:

- Configure the supervisor through the Databricks workspace UI (Agents > Supervisor Agent > Create)
- Add the Neo4j KG Agent as a sub-agent (Type: Agent, Source: the deployed Model Serving endpoint)
- Add the Genie Lakehouse Agent as a sub-agent (Type: Genie Space, Source: the retail Genie Space)
- Provide detailed descriptions for each agent so the supervisor can route accurately:
  - Neo4j KG Agent: "Product search, recommendations, cart operations, inventory checks, and user preference memory"
  - Genie Agent: "Revenue trends, customer segments, order history, basket analysis, and inventory analytics over retail transaction data"
- The supervisor handles intent classification, routing, combined queries, and response synthesis automatically

### R4: Deployment

- The Neo4j KG Agent is logged with MLflow, registered in Unity Catalog, and deployed via `agents.deploy()` (see Phase 3)
- The Genie Lakehouse Agent is configured as a Genie Space in the workspace (see Phase 2)
- The Supervisor Agent is created via AgentBricks in the workspace UI, which automatically deploys it as a Model Serving endpoint with tracing and the Review App enabled

### R5: Evaluation

- Use Mosaic AI Agent Evaluation with a curated set of test questions spanning both agents
- Include questions that require cross-agent reasoning
- Establish baseline quality metrics before production deployment

---

## Implementation Plan

### Phase 1: Analysis

- [ ] Audit all 14 existing tools for Databricks compatibility (identify OpenAI-specific code, local file paths, session state assumptions)
- [ ] Identify which Neo4j connection patterns work from Databricks (network access, secrets management)
- [ ] Verify the lakehouse tables exist in Unity Catalog with correct schemas
- [ ] Document current tool input/output schemas for supervisor routing logic

### Phase 2: Genie Space

- [ ] Create the Genie Space in the Databricks workspace
- [ ] Connect it to the four retail Delta tables
- [ ] Add table/column descriptions, example queries, synonyms, and instructions
- [ ] Test with representative analytics questions and iterate on accuracy
- [ ] Validate the `GenieAgent` wrapper works programmatically

### Phase 3: Neo4j KG Agent — ToolRuntime Refactor

- [ ] Define `RetailContext` dataclass in `dbx_agent/src/retail_context.py`
- [ ] Implement all 14 tools using `ToolRuntime[RetailContext]` injection (see R2)
- [ ] Export a flat `ALL_TOOLS` list — no factory needed
- [ ] Replace `OpenAI`/`AzureOpenAI` LLM with `ChatDatabricks`
- [ ] Store Neo4j credentials in Databricks secrets, load them at agent init
- [ ] Build the LangGraph agent with `create_react_agent(model, ALL_TOOLS, context_schema=RetailContext)`
- [ ] Add thin `ChatAgent` shim for Databricks Model Serving and test in a notebook

### Phase 4: Supervisor (AgentBricks)

- [ ] Create a Databricks Supervisor Agent in the workspace UI
- [ ] Add the Neo4j KG Agent (Model Serving endpoint) as a sub-agent with description
- [ ] Add the Genie Lakehouse Agent (Genie Space) as a sub-agent with description
- [ ] Test with representative queries spanning both agents
- [ ] Verify combined queries route to both agents and synthesize correctly

### Phase 5: Deploy and Evaluate

- [ ] Verify the supervisor's Model Serving endpoint is running
- [ ] Confirm tracing and Review App are enabled on the supervisor endpoint
- [ ] Run the evaluation suite and establish baseline metrics

---

## Key Code Patterns

### Why `ToolRuntime` Over Closure Factories

LangGraph v1 introduced `ToolRuntime[Context]` with `context_schema` on `create_react_agent` for dependency injection. Tools declare what they need; the framework injects it at invocation time. The same tool objects run in any environment — only the context differs.

| | ToolRuntime |
|---|---|
| Dependency binding | Explicit injection at invocation time |
| Environment portability | Same tool objects everywhere |
| Type safety | `RetailContext` dataclass is typed and inspectable |
| Testing | Pass a test `RetailContext` directly |
| MLflow serialization | Plain functions; Models-from-Code works cleanly |

### Step 1: Define the Shared Context

```python
# dbx_agent/src/retail_context.py
from dataclasses import dataclass
from neo4j_agent_memory import MemoryClient

@dataclass
class RetailContext:
    """All external dependencies for retail agent tools.

    Injected by LangGraph at invocation time via ToolRuntime.
    """
    client: MemoryClient
    session_id: str | None = None
```

### Step 2: Tools Using `ToolRuntime`

```python
# dbx_agent/src/product_tools.py
from langchain_core.tools import tool, ToolRuntime
from retail_context import RetailContext

@tool(args_schema=SearchProductsInput)
async def search_products(
    query: str,
    category: str | None = None,
    brand: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
    runtime: ToolRuntime[RetailContext],  # injected by LangGraph, hidden from LLM
) -> str:
    """Search the product catalog by query."""
    client = runtime.context.client
    embedding = await client._embedder.embed(query)
    result = await client.graph.execute_read(cypher, params)
    ...
```

The `runtime` parameter is reserved — LangGraph detects it by type hint and injects it automatically. It never appears in the tool schema sent to the LLM.

### Step 3: Flat Tool List (No Factory)

```python
# dbx_agent/src/react_agent.py
from product_tools import search_products, get_product_details, get_related_products
from memory_tools import remember_message, recall_memory, search_memory

ALL_TOOLS = [
    search_products, get_product_details, get_related_products,
    remember_message, recall_memory, search_memory,
]
```

No factory function. No closures. Tools are plain module-level functions.

### Step 4: Build the Neo4j KG Agent

```python
# dbx_agent/src/react_agent.py
from databricks_langchain import ChatDatabricks
from langgraph.prebuilt import create_react_agent
from retail_context import RetailContext

llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

neo4j_agent = create_react_agent(
    model=llm,
    tools=ALL_TOOLS,
    context_schema=RetailContext,
    prompt=(
        "You are a retail product assistant with access to a Neo4j knowledge graph. "
        "Use your tools to search products, get recommendations, manage carts, "
        "check inventory, and recall user preferences from memory."
    ),
)
```

### Step 5: Invocation — Same Agent, Different Context

```python
# Databricks Model Serving
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
neo4j_uri = w.dbutils.secrets.get("neo4j", "uri")
neo4j_password = w.dbutils.secrets.get("neo4j", "password")
client = MemoryClient(uri=neo4j_uri, password=neo4j_password, ...)
await client.connect()

result = neo4j_agent.invoke(
    {"messages": messages},
    context=RetailContext(client=client, session_id=serving_input.session_id),
)
```

### Step 6: Genie Agent Setup

```python
from databricks_langchain.genie import GenieAgent

genie_agent = GenieAgent(
    genie_space_id="<RETAIL_GENIE_SPACE_ID>",
    genie_agent_name="Retail Analytics Agent",
    description=(
        "Answers questions about retail transaction data: revenue, sales trends, "
        "top products, customer segments, order history, and basket analysis. "
        "Queries structured data in the lakehouse via SQL."
    ),
)
```

### Step 7: Databricks Supervisor Agent (AgentBricks)

Unlike the Neo4j KG Agent which is built in code, the supervisor is created through the Databricks workspace UI — no custom orchestration code required.

1. Navigate to **Agents > Supervisor Agent > Create Supervisor Agent**
2. **Name**: `supervisor-agent-retail` (or auto-generated)
3. **Configure Agents** — add both sub-agents:

| Type | Source | Agent Name | Description |
|------|--------|------------|-------------|
| Agent | Neo4j KG Agent serving endpoint | `neo4j_kg_agent` | Product search, recommendations, cart operations, inventory checks, and user preference memory backed by a Neo4j knowledge graph |
| Genie Space | Retail Genie Space | `retail_analytics` | Revenue trends, customer segments, order history, basket analysis, and inventory analytics over retail transaction data in Unity Catalog |

4. Click **Create Agent** — the supervisor handles intent routing, combined queries, and response synthesis automatically
5. Test via the built-in playground or Review App

The supervisor is deployed as its own Model Serving endpoint with tracing and feedback collection enabled by default.

---

## Example Interactions

| User Question | Routed To | What Happens |
|--------------|-----------|--------------|
| "Find waterproof hiking boots under $150" | Neo4j KG Agent | Vector search + category/price filter on graph |
| "What were our top 10 products by revenue last month?" | Genie Agent | Generates SQL joining transactions + products, returns ranked list |
| "Which of my recommended products are actually trending?" | Both | Neo4j returns personalized recommendations, Genie returns trending products by sales volume, supervisor intersects the lists |
| "Add the Salomon X Ultra to my cart" | Neo4j KG Agent | Product lookup + cart tool |
| "How does average order value compare across customer segments?" | Genie Agent | SQL aggregation over transactions grouped by customer segment |
| "Are there alternatives to this out-of-stock item that sold well last quarter?" | Both | Neo4j finds same-category in-stock alternatives, Genie ranks them by recent sales |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `databricks-langchain` | >=0.15.0 | `GenieAgent`, `ChatDatabricks` |
| `langgraph` | >=0.2 | Neo4j KG Agent (`create_react_agent`) |
| `mlflow` | >=3.1 | Agent logging, registration, tracing |
| `databricks-agents` | >=1.1.0 | `agents.deploy()` for Model Serving |
| `neo4j` | >=5.0 | Neo4j driver for KG agent tools |
| `langchain-core` | >=0.3 | `@tool` decorator, `ToolRuntime` injection |

---

## References

- [Mosaic AI Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [Author AI agents in code](https://docs.databricks.com/aws/en/generative-ai/agent-framework/create-chat-model)
- [Deploy an agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/deploy-agent)
- [What is a Genie Space](https://docs.databricks.com/aws/en/genie/)
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Use Genie in multi-agent systems](https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-genie)
- [Databricks Supervisor Agent (AgentBricks)](https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-systems)
- [Agent system design patterns](https://docs.databricks.com/aws/en/generative-ai/guide/agent-system-design-patterns)
- [Log and register AI agents](https://docs.databricks.com/aws/en/generative-ai/agent-framework/log-agent)
- [LangGraph create_react_agent reference](https://langchain-ai.github.io/langgraph/reference/prebuilt/#create_react_agent)
- [LangChain ToolRuntime / runtime injection](https://python.langchain.com/docs/how_to/tool_configure/)
- [MLflow Models-from-Code for LangGraph](https://mlflow.org/blog/langgraph-model-from-code)
