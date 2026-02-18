# Questions for Phases L4–L6

Questions that need answers before implementing the remaining lakehouse integration phases.

## Phase L4: Lakehouse Agent Tools

1. **SQL connector vs SDK** — Should the agent tools use `databricks-sql-connector` (direct SQL over ODBC/Thrift) or the newer `databricks-sdk` (REST API)? The aircraft workshop may set a precedent here — which does it use?

2. **Tool implementation style** — The current agent tools (in `backend/tools/`) use LangChain `@tool` decorators with Pydantic input schemas. Should the new lakehouse tools follow the exact same pattern in a new `backend/tools/lakehouse.py` module, or is there a preference for a different structure?

3. **SQL generation approach** — Should the lakehouse tools use:
   - **Parameterized queries** — Pre-written SQL templates with parameter substitution (safer, more predictable, limited flexibility)?
   - **Text-to-SQL via Genie** — Let the Databricks Genie agent generate SQL from natural language (more flexible, requires Genie Space setup)?
   - **Hybrid** — Pre-built tools for common queries + Genie fallback for ad-hoc questions?

4. **Connection pooling** — Should the Databricks SQL connection be managed as a singleton (like the Neo4j driver), or created per-request? The SQL Warehouse has cold-start latency, so connection reuse matters.

5. **Optional dependency** — The spec says `databricks-sql-connector` should be an optional dependency in `pyproject.toml`. Should it be an extras group (e.g., `pip install .[databricks]`) or just documented as a manual install?

## Phase L5: Agent Integration

6. **Routing architecture** — The spec mentions two patterns:
   - **Single LangGraph agent** with additional lakehouse tools added to the existing tool set (simpler, current architecture)
   - **Multi-agent supervisor** with a Databricks AgentBricks supervisor routing to Genie Agent vs Neo4j MCP Agent (aircraft workshop pattern, more complex)

   Which approach? The single-agent approach is simpler and keeps the current architecture. The multi-agent approach is closer to the aircraft workshop demo.

7. **System prompt changes** — How much should the system prompt change? Should it:
   - Just mention the new capabilities (minimal change)?
   - Include specific guidance on when to use lakehouse vs graph tools?
   - Include example queries the agent can now answer?

8. **Cross-source query orchestration** — For queries like "What trending running shoes have good reviews?", the agent needs to call both Databricks (trending + reviews) and Neo4j (product details + graph relationships). Should this be:
   - Left to the LLM to figure out tool sequencing?
   - Explicitly guided with a routing prompt?
   - Implemented as a composite tool that calls both backends?

## Phase L6: Workshop Lab Notebooks

9. **Notebook format** — Should the workshop notebooks be:
   - **Databricks notebooks** (`.py` or `.sql` files with `# COMMAND ----------` separators)?
   - **Jupyter notebooks** (`.ipynb`) that can run in Databricks or locally?

10. **Lab scope** — The spec lists 4 labs. Should each be self-contained (15 min each), or do they build on each other sequentially (requiring completion in order)?

11. **Participant prerequisites** — Should the labs assume participants already have:
    - A running Databricks workspace?
    - The Neo4j instance loaded with product data?
    - The retail assistant API running?
    Or should the labs include setup steps for all of these?
