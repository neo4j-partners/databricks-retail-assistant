"""Deployment configuration for the retail agent.

Usage:
    from retail_agent.src.deploy_config import CONFIG, AGENT_NAME, RunMode
"""

import os
from dataclasses import dataclass, field
from enum import Enum

AGENT_NAME = "retail_agent_v3"


class RunMode(Enum):
    """Deployment run modes."""

    DEPLOY = "deploy"
    DELETE = "delete"


@dataclass
class DeployConfig:
    """Configuration for deploying the retail agent to Databricks."""

    # Run mode
    run_mode: RunMode = RunMode.DEPLOY
    wait_for_ready: bool = True
    max_wait_seconds: int = 1200

    # Unity Catalog — matches existing lakehouse_tables.py naming
    catalog: str = "retail_assistant"
    schema: str = "retail"
    model_name: str = AGENT_NAME

    # Endpoint name (auto-generated if empty)
    endpoint_name: str = field(
        default_factory=lambda: os.environ.get("RETAIL_AGENT_ENDPOINT_NAME", "")
    )

    # MLflow
    experiment_name_pattern: str = f"/Users/{{user}}/{AGENT_NAME}"
    run_name: str = AGENT_NAME
    artifact_path: str = AGENT_NAME

    # Databricks secrets (used in Step 3, not Step 2)
    secret_scope: str = "retail-agent-secrets"
    neo4j_uri_secret: str = "neo4j-uri"
    neo4j_password_secret: str = "neo4j-password"

    # LLM — Databricks-hosted, no API key needed
    llm_endpoint: str = "databricks-claude-sonnet-4-6"

    # Embedding — Databricks Foundation Model API (pre-deployed, no setup needed)
    embedding_model: str = "databricks-bge-large-en"
    embedding_dimensions: int = 1024

    # Deployment
    scale_to_zero: bool = True

    # Supervisor (STUB) — see retail_agent/src/supervisor_agent.py
    # Both fields must be set before step7_deploy_supervisor.py can do real work.
    supervisor_model_name: str = "retail_supervisor_v1"
    genie_space_id: str = ""

    # Sample queries for testing
    sample_queries: list[str] = field(
        default_factory=lambda: [
            "Echo hello world",
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


CONFIG = DeployConfig()
