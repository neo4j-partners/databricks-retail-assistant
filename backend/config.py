"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from neo4j_agent_memory import MemorySettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("password")

    openai_api_key: SecretStr | None = None

    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_llm_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_embedding_dimensions: int = 1536

    llm_provider: str = "openai"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


def get_memory_settings() -> MemorySettings:
    """Create MemorySettings from environment."""
    s = get_settings()
    api_key = s.openai_api_key or s.azure_openai_api_key

    embedding_config: dict[str, Any] = {
        "provider": "openai",
        "model": s.azure_openai_embedding_deployment or "text-embedding-3-small",
        "dimensions": s.azure_openai_embedding_dimensions,
    }
    if api_key:
        embedding_config["api_key"] = api_key

    return MemorySettings(
        neo4j={
            "uri": s.neo4j_uri,
            "username": s.neo4j_username,
            "password": s.neo4j_password,
        },
        embedding=embedding_config,
    )
