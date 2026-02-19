"""ChatAgent shim for Databricks Model Serving.

Thin adapter that translates the Databricks serving protocol to
LangGraph's invoke() interface. This is the Step 2 prototype — no
async, no secrets, no lazy init needed (the echo tool has no deps).

References:
    - LANGCHAIN_AGENT.md Section 6 (ChatAgent adapter pattern)
    - aircraft_analyst mlflow_model.py (ResponsesAgent pattern — this
      prototype uses the simpler ChatAgent interface instead)
"""

import mlflow
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

from agent import create_prototype_agent


class PrototypeAgent(ChatAgent):
    """Minimal ChatAgent wrapper around the LangGraph echo agent."""

    def __init__(self):
        self._agent = None

    def _ensure_initialized(self):
        """Create the agent on first call.

        Lazy init is not strictly needed for Step 2 (no secrets), but
        we use the pattern anyway to match the production shape from
        LANGCHAIN_AGENT.md Section 6.
        """
        if self._agent is None:
            mlflow.langchain.autolog()
            self._agent = create_prototype_agent()

    def predict(self, messages, context=None, custom_inputs=None):
        """Sync entry point required by Databricks Model Serving.

        For Step 2 the echo tool is sync, so no asyncio.run() bridge
        is needed. Step 3 will add the async bridge per LANGCHAIN_AGENT.md.
        """
        self._ensure_initialized()
        request = {"messages": [{"role": m.role, "content": m.content} for m in messages]}
        result = self._agent.invoke(request)

        # Extract the final AI message from LangGraph output
        ai_messages = [
            ChatAgentMessage(role="assistant", content=msg.content)
            for msg in result["messages"]
            if hasattr(msg, "type") and msg.type == "ai" and msg.content
        ]

        if not ai_messages:
            ai_messages = [ChatAgentMessage(role="assistant", content="No response generated.")]

        return ChatAgentResponse(messages=ai_messages)


AGENT = PrototypeAgent()
mlflow.models.set_model(AGENT)
