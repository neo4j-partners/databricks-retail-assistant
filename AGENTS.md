# Multi-Agent Retail Assistant on Databricks

## Problem Statement

The current backend is a FastAPI application running locally with 14 LangChain tools (product search, recommendations, cart, inventory, memory) backed by a Neo4j knowledge graph. The chat endpoints are placeholders — no agent is wired in yet (Phase 7). Meanwhile, the lakehouse holds 500K+ orders and 1.15M line items in Delta tables that are completely disconnected from the assistant.

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

The supervisor is a LangGraph graph that receives the user message, classifies intent, delegates to the appropriate sub-agent(s), and returns a unified response. It is wrapped as a `ChatAgent`, logged with MLflow, registered in Unity Catalog, and deployed to a Model Serving endpoint with `agents.deploy()`.

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
                   |  (LangGraph) |
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

**Supervisor** — A LangGraph `StateGraph` with conditional routing. The LLM reads agent descriptions and the user query, then decides which agent(s) to invoke. If both agents return results, the supervisor synthesizes a combined answer.

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

### R2: Neo4j KG Agent as a Databricks-Compatible Agent

Refactor the existing tools layer into a standalone agent that can run inside Databricks:

- Wrap the 14 LangChain tools in a LangGraph `StateGraph` using the existing `create_tools(client)` factory
- Use `ChatDatabricks` as the LLM (Llama 3.3 70B or DBRX) instead of OpenAI
- Package the Neo4j connection credentials as Databricks secrets
- The agent must conform to the `ChatAgent` interface (`predict` and `predict_stream` methods)

### R3: Multi-Agent Supervisor

Build a LangGraph supervisor that coordinates the two agents:

- The supervisor receives the user message and classifies intent into: `graph_query`, `analytics_query`, or `combined_query`
- `graph_query` — product search, recommendations, cart ops, inventory checks — routes to Neo4j KG Agent
- `analytics_query` — revenue, trends, customer segments, order history — routes to Genie Agent
- `combined_query` — e.g., "recommend trending products in my price range" — routes to both, then synthesizes
- The supervisor passes conversation context between agents when needed

### R4: MLflow Registration and Deployment

- Log the supervisor agent with MLflow, declaring all resource dependencies (LLM endpoint, Genie Space, SQL warehouse)
- Register in Unity Catalog as `retail.agents.retail_supervisor`
- Deploy via `agents.deploy()` with scale-to-zero enabled
- Enable MLflow tracing for observability and the Review App for stakeholder feedback

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

### Phase 3: Neo4j KG Agent

- [ ] Extract the tools layer from the FastAPI backend into a standalone module
- [ ] Replace `OpenAI`/`AzureOpenAI` LLM with `ChatDatabricks`
- [ ] Store Neo4j credentials in Databricks secrets, load them at agent init
- [ ] Build the LangGraph tool-calling agent using the existing tools
- [ ] Wrap in `ChatAgent` interface and test in a notebook

### Phase 4: Supervisor

- [ ] Build the LangGraph supervisor `StateGraph` with routing logic
- [ ] Wire in both sub-agents (Neo4j KG Agent as a node, GenieAgent as a node)
- [ ] Implement the intent classifier (LLM-based, using agent descriptions)
- [ ] Handle combined queries with parallel invocation and response synthesis
- [ ] Wrap in `ChatAgent` and test end-to-end in a notebook

### Phase 5: Deploy

- [ ] Log the supervisor with MLflow, declaring resource dependencies
- [ ] Register in Unity Catalog
- [ ] Deploy with `agents.deploy()`
- [ ] Verify the serving endpoint, Review App, and tracing are functional
- [ ] Run the evaluation suite and establish baseline metrics

---

## Key Code Patterns

### Genie Agent Setup

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

### Neo4j KG Agent Setup

```python
from databricks_langchain import ChatDatabricks
from langgraph.prebuilt import create_react_agent
from backend.tools import create_tools

llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
tools = create_tools(memory_client)

neo4j_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=(
        "You are a retail product assistant with access to a Neo4j knowledge graph. "
        "Use your tools to search products, get recommendations, manage carts, "
        "check inventory, and recall user preferences from memory."
    ),
)
```

### Supervisor with LangGraph

```python
from langgraph.graph import StateGraph, END
from mlflow.langchain.chat_agent_langgraph import ChatAgentState, ChatAgentToolNode

def create_supervisor(neo4j_agent, genie_agent, llm):
    def route(state: ChatAgentState):
        """LLM-based router that classifies intent."""
        last_message = state["messages"][-1]["content"]
        classification = llm.invoke([
            {"role": "system", "content": (
                "Classify the user query into one of: "
                "graph_query (product search, recommendations, cart, inventory), "
                "analytics_query (revenue, trends, segments, order history), "
                "combined_query (needs both). Respond with only the label."
            )},
            {"role": "user", "content": last_message},
        ])
        return classification.content.strip()

    def call_neo4j(state, config):
        result = neo4j_agent.invoke(state, config)
        return {"messages": result["messages"]}

    def call_genie(state, config):
        result = genie_agent.invoke(state, config)
        return {"messages": result["messages"]}

    def synthesize(state, config):
        """Combine results from both agents into a unified response."""
        response = llm.invoke([
            {"role": "system", "content": "Synthesize the following agent responses into a single coherent answer."},
            *state["messages"],
        ])
        return {"messages": [response]}

    workflow = StateGraph(ChatAgentState)
    workflow.add_node("neo4j", call_neo4j)
    workflow.add_node("genie", call_genie)
    workflow.add_node("synthesize", synthesize)
    workflow.set_entry_point("router")
    workflow.add_node("router", lambda s: s)  # pass-through

    workflow.add_conditional_edges("router", route, {
        "graph_query": "neo4j",
        "analytics_query": "genie",
        "combined_query": "neo4j",  # neo4j first, then genie, then synthesize
    })
    workflow.add_edge("neo4j", END)  # direct graph queries end here
    workflow.add_edge("genie", END)  # direct analytics queries end here
    # combined path: neo4j -> genie -> synthesize -> END
    # (conditional edges handle this in the full implementation)

    return workflow.compile()
```

### MLflow Logging and Deployment

```python
import mlflow
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksGenieSpace,
    DatabricksSQLWarehouse,
)
from databricks import agents

resources = [
    DatabricksServingEndpoint(endpoint_name="databricks-meta-llama-3-3-70b-instruct"),
    DatabricksGenieSpace(genie_space_id="<RETAIL_GENIE_SPACE_ID>"),
    DatabricksSQLWarehouse(warehouse_id="<SQL_WAREHOUSE_ID>"),
]

with mlflow.start_run():
    logged = mlflow.pyfunc.log_model(
        artifact_path="retail_supervisor",
        python_model="supervisor_agent.py",
        pip_requirements=[
            "mlflow>=3.1",
            "langgraph",
            "databricks-langchain>=0.15",
            "neo4j",
        ],
        resources=resources,
    )

mlflow.set_registry_uri("databricks-uc")
mlflow.register_model(logged.model_uri, "retail.agents.retail_supervisor")

deployment = agents.deploy(
    model_name="retail.agents.retail_supervisor",
    model_version=1,
    scale_to_zero_enabled=True,
)
```

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
| `langgraph` | >=0.2 | Agent graphs, supervisor orchestration |
| `mlflow` | >=3.1 | Agent logging, registration, tracing |
| `databricks-agents` | >=1.1.0 | `agents.deploy()` for Model Serving |
| `neo4j` | >=5.0 | Neo4j driver for KG agent tools |
| `langchain-core` | >=0.3 | Tool decorator, base classes |

---

## References

- [Mosaic AI Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [Author AI agents in code](https://docs.databricks.com/aws/en/generative-ai/agent-framework/create-chat-model)
- [Deploy an agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/deploy-agent)
- [What is a Genie Space](https://docs.databricks.com/aws/en/genie/)
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Use Genie in multi-agent systems](https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-genie)
- [Agent system design patterns](https://docs.databricks.com/aws/en/generative-ai/guide/agent-system-design-patterns)
- [LangGraph multi-agent Genie notebook](https://docs.databricks.com/notebooks/source/generative-ai/langgraph-multiagent-genie.html)
- [Log and register AI agents](https://docs.databricks.com/aws/en/generative-ai/agent-framework/log-agent)
