"""Databricks Foundation Model API embedder for neo4j-graphrag-python.

Subclasses the neo4j-graphrag Embedder interface so the library's pipelines
and retrievers can use Databricks-hosted embedding models.

Runs on a Databricks cluster where mlflow is available. No API keys needed —
authentication is handled by the cluster's own identity.

Usage (on cluster):
    from databricks_embedder import DatabricksEmbedder
    embedder = DatabricksEmbedder()
    vector = embedder.embed_query("running shoes for beginners")
"""

import logging

import mlflow.deployments
from neo4j_graphrag.embeddings.base import Embedder

from deploy_config import CONFIG

logger = logging.getLogger(__name__)


class DatabricksEmbedder(Embedder):
    """Embedder using Databricks Foundation Model API via mlflow.deployments.

    Implements embed_query(text) -> list[float] as required by the
    neo4j-graphrag Embedder interface. The base class provides a default
    async_embed_query that delegates to embed_query synchronously, which
    is the standard pattern across all embedder implementations in the
    neo4j-graphrag library.
    """

    def __init__(
        self,
        model: str = CONFIG.embedding_model,
        dimensions: int = CONFIG.embedding_dimensions,
    ):
        super().__init__()
        self.model = model
        self.dimensions = dimensions
        self._client = mlflow.deployments.get_deploy_client("databricks")

    def embed_query(self, text: str) -> list[float]:
        """Embed query text using Databricks Foundation Model API.

        Args:
            text: Text to convert to a vector embedding.

        Returns:
            A vector embedding as a list of floats.
        """
        response = self._client.predict(
            endpoint=self.model,
            inputs={"input": [text]},
        )
        embedding = response["data"][0]["embedding"]

        if len(embedding) != self.dimensions:
            logger.warning(
                "Dimension mismatch: expected %d, got %d",
                self.dimensions,
                len(embedding),
            )

        return embedding
