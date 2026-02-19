"""ChatAgent shim for Databricks Model Serving.

Step 3 prototype from PROTOTYPE.md. Builds on Step 2 by adding:
- Lazy MemoryClient init from secrets (NEO4J_URI, NEO4J_PASSWORD)
- asyncio.run() bridge from sync predict() to async ainvoke()
- RetailContext injection into the LangGraph agent

References:
    - LANGCHAIN_AGENT.md Section 6 (ChatAgent adapter pattern)
    - PROTOTYPE.md Step 3 (neo4j-agent-memory integration)
"""

import asyncio
import os
from uuid import uuid4

import mlflow
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

from agent import create_prototype_agent
from context import RetailContext


class PrototypeAgent(ChatAgent):
    """ChatAgent wrapper with Neo4j memory integration."""

    def __init__(self):
        # All attributes must be defined in __init__ (MLflow requirement)
        self._agent = None
        self._initialized = False
        self._init_error: str | None = None
        self._client = None

    def _ensure_initialized(self):
        """Lazy initialization of agent and MemoryClient.

        Follows the aircraft_analyst pattern: catches all exceptions and
        stores them in _init_error rather than crashing. predict() checks
        _init_error and returns an error message to the caller.

        During log_model() validation, secrets aren't available — we detect
        this and skip init so predict() can return a placeholder response.
        """
        if self._initialized:
            return

        # Secrets not available during log_model() — skip init
        if "NEO4J_URI" not in os.environ or "NEO4J_PASSWORD" not in os.environ:
            return

        try:
            from neo4j_agent_memory import MemoryClient, MemorySettings, Neo4jConfig
            from pydantic import SecretStr

            mlflow.langchain.autolog()

            settings = MemorySettings(
                neo4j=Neo4jConfig(
                    uri=os.environ["NEO4J_URI"],
                    password=SecretStr(os.environ["NEO4J_PASSWORD"]),
                ),
            )
            self._client = MemoryClient(settings)
            self._agent = create_prototype_agent()
            self._initialized = True
            self._init_error = None

        except Exception as e:
            import traceback

            self._init_error = f"Failed to initialize agent: {e}\n{traceback.format_exc()}"
            self._agent = None

    def predict(self, messages, context=None, custom_inputs=None):
        """Sync entry point required by Databricks Model Serving.

        Bridges to async via asyncio.run() because all memory tools and
        the MemoryClient are async-only. See LANGCHAIN_AGENT.md
        "Async Tools in Model Serving" section.

        Uses nest_asyncio when an event loop is already running (Databricks
        notebook / IPython kernel during log_model() validation).
        """
        self._ensure_initialized()

        # Not yet initialized — either log_model() validation (no secrets)
        # or a real init error at serving time.
        if self._agent is None:
            error_msg = self._init_error or "Agent not initialized (secrets not available during model logging)."
            return ChatAgentResponse(
                messages=[ChatAgentMessage(
                    role="assistant",
                    content=f"Error: {error_msg}",
                    id=str(uuid4()),
                )]
            )

        try:
            asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
        except RuntimeError:
            pass
        return asyncio.run(self._async_predict(messages, context, custom_inputs))

    async def _async_predict(self, messages, context, custom_inputs):
        """Async implementation — connects MemoryClient and invokes agent."""
        # Connect MemoryClient if not already connected (async operation)
        if self._client and not self._client.is_connected:
            await self._client.connect()

        # Extract session_id from custom_inputs or generate one
        session_id = None
        if custom_inputs and isinstance(custom_inputs, dict):
            session_id = custom_inputs.get("session_id")
        if not session_id:
            session_id = "serving-default"

        # Build context with session_id for this request
        retail_context = RetailContext(
            client=self._client,
            session_id=session_id,
        )

        request = {"messages": [{"role": m.role, "content": m.content} for m in messages]}
        result = await self._agent.ainvoke(request, context=retail_context)

        # Extract the final AI message from LangGraph output
        ai_messages = [
            ChatAgentMessage(role="assistant", content=msg.content, id=str(uuid4()))
            for msg in result["messages"]
            if hasattr(msg, "type") and msg.type == "ai" and msg.content
        ]

        if not ai_messages:
            ai_messages = [ChatAgentMessage(role="assistant", content="No response generated.", id=str(uuid4()))]

        return ChatAgentResponse(messages=ai_messages)


AGENT = PrototypeAgent()
mlflow.models.set_model(AGENT)
