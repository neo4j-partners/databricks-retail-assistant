"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j_agent_memory import MemoryClient

from backend import dependencies
from backend.config import get_memory_settings, get_settings
from backend.routes import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle."""
    logger.info("Connecting to Neo4j...")
    dependencies.memory_client = MemoryClient(get_memory_settings())
    await dependencies.memory_client.connect()
    logger.info("Connected to Neo4j")

    yield

    if dependencies.memory_client:
        await dependencies.memory_client.close()
        logger.info("Disconnected from Neo4j")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Smart Shopping Assistant API",
        description="Retail assistant powered by LangGraph and Neo4j Agent Memory",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app
