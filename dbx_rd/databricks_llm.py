"""Databricks Foundation Model API LLM for neo4j-graphrag-python.

Subclasses the neo4j-graphrag LLMInterfaceV2 so the library's pipelines
and retrievers can use Databricks-hosted LLMs.

Runs on a Databricks cluster where mlflow is available. No API keys needed —
authentication is handled by the cluster's own identity.

Usage (on cluster):
    from databricks_llm import DatabricksLLM
    llm = DatabricksLLM()
    response = llm.invoke([{"role": "user", "content": "Hello"}])
    print(response.content)
"""

import logging
from typing import Any, List, Optional, Type, Union

import mlflow.deployments
from neo4j_graphrag.llm.base import LLMInterfaceV2
from neo4j_graphrag.llm.types import LLMResponse
from neo4j_graphrag.types import LLMMessage
from pydantic import BaseModel

from deploy_config import CONFIG

logger = logging.getLogger(__name__)


class DatabricksLLM(LLMInterfaceV2):
    """LLM using Databricks Foundation Model API via mlflow.deployments.

    Implements invoke() and ainvoke() as required by the neo4j-graphrag
    LLMInterfaceV2 interface.

    ainvoke delegates to invoke synchronously because mlflow.deployments
    has no async client. This matches the pattern in the neo4j-graphrag
    library's embedder base class (async_embed_query delegates to
    embed_query) and the proven pattern in step5_demo_retrievers.py.
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
        input: Union[str, List[LLMMessage]],
        response_format: Optional[Union[Type[BaseModel], dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send messages to the LLM and return a response.

        Accepts both List[LLMMessage] (V2 interface) and str (V1 legacy)
        so it works with both SimpleKGPipeline and Text2CypherRetriever.

        Args:
            input: Messages as a list of LLMMessage dicts, or a plain string.
            response_format: Not supported by Databricks Foundation Model API.
            **kwargs: Additional keyword arguments (unused).

        Returns:
            LLMResponse with the model's text response.
        """
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        else:
            messages = [
                {"role": msg["role"], "content": msg["content"]} for msg in input
            ]

        params = {"messages": messages, "max_tokens": 2048}
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
        input: Union[str, List[LLMMessage]],
        response_format: Optional[Union[Type[BaseModel], dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Async version — delegates to invoke (mlflow has no async client)."""
        return self.invoke(input, response_format=response_format)
