"""Deployment configuration for the retail agent prototype.

Ported from aircraft_analyst/src/graph_agent/config.py with retail-specific
defaults. See LANGCHAIN_AGENT.md Section 7 for the production version.

All settings can be overridden via environment variables using the
pattern: RETAIL_AGENT_<SETTING_NAME>.

Usage:
    from dbx_agent.config import CONFIG, RunMode

    # Override via env: RETAIL_AGENT_RUN_MODE=delete
"""

import os
from dataclasses import dataclass, field
from enum import Enum


class RunMode(Enum):
    """Deployment run modes."""

    DEPLOY = "deploy"
    DELETE = "delete"


@dataclass
class DeployConfig:
    """Configuration for deploying the prototype agent to Databricks."""

    # Run mode
    run_mode: RunMode = RunMode.DEPLOY
    wait_for_ready: bool = True
    max_wait_seconds: int = 600

    # Unity Catalog — matches existing lakehouse_tables.py naming
    catalog: str = "retail_assistant"
    schema: str = "retail"
    model_name: str = "dbx_agent_prototype"

    # Endpoint name (auto-generated if empty)
    endpoint_name: str = ""

    # MLflow
    experiment_name_pattern: str = "/Users/{user}/retail_agent_prototype"
    run_name: str = "retail_agent_prototype"
    artifact_path: str = "dbx_agent_prototype"

    # Databricks secrets (used in Step 3, not Step 2)
    secret_scope: str = "retail-agent-secrets"
    neo4j_uri_secret: str = "neo4j-uri"
    neo4j_password_secret: str = "neo4j-password"

    # LLM — Databricks-hosted, no API key needed
    llm_endpoint: str = "databricks-meta-llama-3-3-70b-instruct"

    # Embedding — Databricks Foundation Model API (pre-deployed, no setup needed)
    embedding_model: str = "databricks-bge-large-en"
    embedding_dimensions: int = 1024

    # Deployment
    scale_to_zero: bool = True

    # Sample queries for testing
    sample_queries: list[str] = field(
        default_factory=lambda: [
            "Echo hello world",
            "Remember that my favorite color is blue",
            "What do you remember about me?",
            "Search for running shoes under $200",
            "Get details for product 'nike-pegasus-40'",
            "What products are related to 'brooks-ghost-16'?",
        ]
    )

    @property
    def uc_model_name(self) -> str:
        """Full Unity Catalog model name."""
        return f"{self.catalog}.{self.schema}.{self.model_name}"

    @property
    def resolved_endpoint_name(self) -> str:
        """Endpoint name (auto-generated if not set)."""
        if self.endpoint_name:
            return self.endpoint_name
        return f"agents_{self.catalog}-{self.schema}-{self.model_name}"

    def get_experiment_name(self, user: str) -> str:
        """Get experiment name with user substitution."""
        return self.experiment_name_pattern.replace("{user}", user)

    def get_environment_vars(self) -> dict[str, str]:
        """Get secret-backed environment variables for the serving endpoint.

        Step 3: Neo4j secrets for MemoryClient connection.
        Uses the {{secrets/scope/key}} pattern per LANGCHAIN_AGENT.md Section 7.
        """
        return {
            "NEO4J_URI": f"{{{{secrets/{self.secret_scope}/{self.neo4j_uri_secret}}}}}",
            "NEO4J_PASSWORD": f"{{{{secrets/{self.secret_scope}/{self.neo4j_password_secret}}}}}",
        }


def _load_config_from_env() -> DeployConfig:
    """Load configuration with environment variable overrides."""
    run_mode_str = os.getenv("RETAIL_AGENT_RUN_MODE", "deploy").lower()
    run_mode = RunMode.DELETE if run_mode_str == "delete" else RunMode.DEPLOY

    return DeployConfig(
        run_mode=run_mode,
        wait_for_ready=os.getenv("RETAIL_AGENT_WAIT_FOR_READY", "true").lower() == "true",
        max_wait_seconds=int(os.getenv("RETAIL_AGENT_MAX_WAIT_SECONDS", "600")),
        catalog=os.getenv("RETAIL_AGENT_CATALOG", "retail_assistant"),
        schema=os.getenv("RETAIL_AGENT_SCHEMA", "retail"),
        model_name=os.getenv("RETAIL_AGENT_MODEL_NAME", "dbx_agent_prototype"),
        endpoint_name=os.getenv("RETAIL_AGENT_ENDPOINT_NAME", ""),
        experiment_name_pattern=os.getenv(
            "RETAIL_AGENT_EXPERIMENT_NAME", "/Users/{user}/retail_agent_prototype"
        ),
        run_name=os.getenv("RETAIL_AGENT_RUN_NAME", "retail_agent_prototype"),
        artifact_path=os.getenv("RETAIL_AGENT_ARTIFACT_PATH", "dbx_agent_prototype"),
        secret_scope=os.getenv("RETAIL_AGENT_SECRET_SCOPE", "retail-agent-secrets"),
        llm_endpoint=os.getenv(
            "RETAIL_AGENT_LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct"
        ),
        embedding_model=os.getenv(
            "RETAIL_AGENT_EMBEDDING_MODEL", "databricks-bge-large-en"
        ),
        embedding_dimensions=int(os.getenv("RETAIL_AGENT_EMBEDDING_DIMENSIONS", "1024")),
        scale_to_zero=os.getenv("RETAIL_AGENT_SCALE_TO_ZERO", "true").lower() == "true",
    )


CONFIG = _load_config_from_env()
