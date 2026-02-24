# Future Improvements: Agent Framework Migration

## Summary of Findings (Feb 2026)

### 1. `ChatAgent` is Now Legacy

The official Databricks docs (updated Feb 2026) explicitly label `ChatAgent` as a **legacy schema** and recommend migrating to `ResponsesAgent`:

> "Databricks recommends migrating to the `ResponsesAgent` schema to author agents."

The current codebase uses `PrototypeAgent(ChatAgent)` in `retail_agent/src/serving_adapter.py` with a separate `create_prototype_agent()` factory in `retail_agent/src/react_agent.py`. This matches the official LangGraph example notebook pattern but is now classified as legacy.

### 2. Two Deployment Paths Now Exist

| Path | Status | Details |
|------|--------|---------|
| **Databricks Apps + `ResponsesAgent`** | Recommended | Uses MLflow `AgentServer` (async FastAPI), any agent framework, deployed via `databricks apps deploy` |
| **Model Serving + `agents.deploy()` + `ChatAgent`** | Legacy (still works) | Current approach in this project |

### 3. Current Pattern Matches the Official LangGraph Example

The official LangGraph tool-calling agent notebook demonstrates the same architecture we use:

- A `ChatAgent` wrapper class with the agent passed in
- Agent created separately via a factory function
- `mlflow.models.set_model(AGENT)` at module level
- Deployed via `agents.deploy()`

### 4. Lazy Initialization Is a Reasonable Deviation

The official example uses **eager initialization** at module level. Our code uses **lazy initialization** in `_ensure_initialized()` because Neo4j secrets aren't available during `log_model()` validation. The official docs don't address this case because they use Databricks-native resources (serving endpoints, vector search) which get automatic auth passthrough.

### 5. Async Background Loop Is Custom

The official examples use synchronous LangGraph `.stream()` / `.invoke()`. Our persistent background event loop (`_create_background_loop()`) is needed specifically for the async Neo4j driver, which is outside the scope of what Databricks documents.

### 6. `ResponsesAgent` Benefits

If migrating in the future, `ResponsesAgent` provides:

- Multi-agent support
- Streaming output with delta events
- Comprehensive tool-calling message history
- Automatic MLflow tracing
- Compatibility with OpenAI Responses schema
- Out-of-the-box compatibility with AI Playground, Agent Evaluation, and Agent Monitoring

## References

- [Create an AI Agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/create-agent) — Overview of agent creation methods on Databricks
- [Author an AI Agent and Deploy on Databricks Apps](https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent) — Recommended `ResponsesAgent` + Databricks Apps approach (updated Feb 23, 2026)
- [Legacy Input and Output Agent Schema (Model Serving)](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-legacy-schema) — `ChatAgent` documentation, now classified as legacy (updated Feb 10, 2026)
- [LangGraph Tool-Calling Agent Notebook](https://docs.databricks.com/aws/en/notebooks/source/generative-ai/langgraph-tool-calling-agent.html) — Official example using `ChatAgent` + LangGraph with `agents.deploy()`
- [MLflow ResponsesAgent Documentation](https://mlflow.org/docs/latest/genai/serving/responses-agent) — MLflow docs for the new `ResponsesAgent` interface
- [MLflow ChatAgent Documentation](https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html#mlflow.pyfunc.ChatAgent) — MLflow docs for the legacy `ChatAgent` interface
- [Migrate an Agent from Model Serving to Databricks Apps](https://docs.databricks.com/aws/en/generative-ai/agent-framework/migrate-agent-to-apps) — Migration guide
