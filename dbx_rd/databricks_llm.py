"""Databricks Foundation Model API LLM for neo4j-graphrag-python.

Subclasses the neo4j-graphrag LLMInterface (V1) so the library's
SimpleKGPipeline can use Databricks-hosted LLMs. The pipeline config
validates against LLMInterface, not LLMInterfaceV2.

Runs on a Databricks cluster where mlflow is available. No API keys needed —
authentication is handled by the cluster's own identity.

Usage (on cluster):
    from databricks_llm import DatabricksLLM
    llm = DatabricksLLM()
    response = llm.invoke("Hello")
    print(response.content)
"""

import logging
from typing import Any, List, Optional, Union

import mlflow.deployments
from neo4j_graphrag.llm.base import LLMInterface
from neo4j_graphrag.llm.types import LLMResponse
from neo4j_graphrag.message_history import MessageHistory
from neo4j_graphrag.types import LLMMessage

from deploy_config import CONFIG

logger = logging.getLogger(__name__)


class DatabricksLLM(LLMInterface):
    """LLM using Databricks Foundation Model API via mlflow.deployments.

    Implements invoke() and ainvoke() as required by the neo4j-graphrag
    LLMInterface (V1). The pipeline's entity extractor calls
    ainvoke(prompt: str) with a plain string.

    ainvoke delegates to invoke synchronously because mlflow.deployments
    has no async client.
    """

    def __init__(
        self,
        model_id: str = CONFIG.llm_endpoint,
        model_params: Optional[dict[str, Any]] = None,
    ):
        super().__init__(model_name=model_id, model_params=model_params)
        self.model_id = model_id
        self._client = mlflow.deployments.get_deploy_client("databricks")

    def invoke(
        self,
        input: str,
        message_history: Optional[Union[List[LLMMessage], MessageHistory]] = None,
        system_instruction: Optional[str] = None,
    ) -> LLMResponse:
        """Send a text prompt to the LLM and return a response.

        Args:
            input: Text prompt sent to the LLM.
            message_history: Optional previous messages for context.
            system_instruction: Optional system message override.

        Returns:
            LLMResponse with the model's text response.
        """
        messages: list[dict[str, str]] = []

        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        if message_history:
            if isinstance(message_history, MessageHistory):
                history = message_history.messages
            else:
                history = message_history
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": input})

        params: dict[str, Any] = {"messages": messages, "max_tokens": 2048}
        if self.model_params:
            params.update(self.model_params)

        response = self._client.predict(
            endpoint=self.model_id,
            inputs=params,
        )
        content = response["choices"][0]["message"]["content"]
        return LLMResponse(content=content)

    async def ainvoke(
        self,
        input: str,
        message_history: Optional[Union[List[LLMMessage], MessageHistory]] = None,
        system_instruction: Optional[str] = None,
    ) -> LLMResponse:
        """Async version — delegates to invoke (mlflow has no async client)."""
        return self.invoke(input, message_history=message_history, system_instruction=system_instruction)
