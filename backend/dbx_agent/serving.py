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
        self._agent = None
        self._client = None
        self._context = None

    def _ensure_initialized(self):
        """Create the agent and MemoryClient on first call.

        Lazy init is required because secrets (NEO4J_URI, NEO4J_PASSWORD)
        are not available during log_model() — they are injected at serving
        time via Databricks secret-backed environment variables.
        """
        if self._agent is not None:
            return

        from neo4j_agent_memory import MemoryClient, MemorySettings, Neo4jConfig
        from pydantic import SecretStr

        settings = MemorySettings(
            neo4j=Neo4jConfig(
                uri=os.environ["NEO4J_URI"],
                password=SecretStr(os.environ["NEO4J_PASSWORD"]),
            ),
        )
        self._client = MemoryClient(settings)
        self._context = RetailContext(client=self._client)

        mlflow.langchain.autolog()
        self._agent = create_prototype_agent()

    def predict(self, messages, context=None, custom_inputs=None):
        """Sync entry point required by Databricks Model Serving.

        Bridges to async via asyncio.run() because all memory tools and
        the MemoryClient are async-only. See LANGCHAIN_AGENT.md
        "Async Tools in Model Serving" section.
        """
        return asyncio.run(self._async_predict(messages, context, custom_inputs))

    async def _async_predict(self, messages, context, custom_inputs):
        """Async implementation — connects MemoryClient and invokes agent."""
        self._ensure_initialized()

        # Connect MemoryClient if not already connected
        if not self._client.is_connected:
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
