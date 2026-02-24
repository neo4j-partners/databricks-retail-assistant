"""ChatAgent shim for Databricks Model Serving.

Step 3 prototype from PROTOTYPE.md. Builds on Step 2 by adding:
- Lazy MemoryClient init from secrets (NEO4J_URI, NEO4J_PASSWORD)
- Persistent event loop in a background thread for async bridging
- RetailContext injection into the LangGraph agent

References:
    - LANGCHAIN_AGENT.md Section 6 (ChatAgent adapter pattern)
    - PROTOTYPE.md Step 3 (neo4j-agent-memory integration)
    - neo4j-agent-memory integrations/base.py (run_sync pattern)
"""

import asyncio
import os
import threading
import traceback
from uuid import uuid4

import mlflow
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

from react_agent import create_prototype_agent
from retail_context import RetailContext


def _create_background_loop() -> asyncio.AbstractEventLoop:
    """Create a persistent event loop running in a background thread.

    This avoids the "async driver bound to wrong event loop" problem:
    asyncio.run() creates and destroys a new loop each time, but the
    Neo4j async driver is bound to the loop it was connected on. By
    keeping one loop alive, all async work (connect, tool calls, etc.)
    runs on the same loop across requests.
    """
    loop = asyncio.new_event_loop()

    def _run(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_run, args=(loop,), daemon=True)
    thread.start()
    return loop


class PrototypeAgent(ChatAgent):
    """ChatAgent wrapper with Neo4j memory integration."""

    def __init__(self):
        # All attributes must be defined in __init__ (MLflow requirement)
        self._agent = None
        self._initialized = False
        self._init_error: str | None = None
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None

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
            from neo4j_agent_memory import (
                EmbeddingConfig,
                MemoryClient,
                MemorySettings,
                Neo4jConfig,
            )
            from pydantic import SecretStr

            from databricks_embedder import DatabricksEmbedder

            mlflow.langchain.autolog()

            # Create persistent event loop before anything async
            self._loop = _create_background_loop()

            # Create Databricks embedder for semantic memory search.
            # Uses mlflow.deployments which handles auth automatically
            # inside the Model Serving container.
            embedding_model = os.environ.get(
                "RETAIL_AGENT_EMBEDDING_MODEL", "databricks-bge-large-en"
            )
            embedding_dims = int(os.environ.get(
                "RETAIL_AGENT_EMBEDDING_DIMENSIONS", "1024"
            ))

            settings = MemorySettings(
                neo4j=Neo4jConfig(
                    uri=os.environ["NEO4J_URI"],
                    password=SecretStr(os.environ["NEO4J_PASSWORD"]),
                ),
                embedding=EmbeddingConfig(
                    dimensions=embedding_dims,
                ),
            )
            embedder = DatabricksEmbedder(
                model=embedding_model,
                dims=embedding_dims,
            )
            if not embedder.validate_endpoint():
                embedder = None

            self._client = MemoryClient(settings, embedder=embedder)

            # Connect MemoryClient on the persistent loop so the Neo4j
            # driver is bound to it from the start
            future = asyncio.run_coroutine_threadsafe(
                self._client.connect(), self._loop
            )
            future.result(timeout=30)

            self._agent = create_prototype_agent()
            self._initialized = True
            self._init_error = None

        except Exception as e:
            self._init_error = f"Failed to initialize agent: {e}\n{traceback.format_exc()}"
            self._agent = None

    def predict(self, messages, context=None, custom_inputs=None):
        """Sync entry point required by Databricks Model Serving.

        Dispatches async work to the persistent background event loop
        via run_coroutine_threadsafe(). This ensures the Neo4j async
        driver always runs on the same loop it was connected on.
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

        future = asyncio.run_coroutine_threadsafe(
            self._async_predict(messages, context, custom_inputs),
            self._loop,
        )
        return future.result(timeout=120)

    async def _async_predict(self, messages, context, custom_inputs):
        """Async implementation — invokes agent with RetailContext."""
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
