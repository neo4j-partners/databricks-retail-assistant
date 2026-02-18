"""FastAPI server for the retail shopping assistant.

This server provides:
- SSE streaming for chat responses (placeholder until agent is wired up)
- Memory context, graph visualization, and preferences endpoints (backed by Neo4j)
- Product search, detail, and related product endpoints (fully functional)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings
from sse_starlette.sse import EventSourceResponse

from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Settings ---


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"

    openai_api_key: str | None = None

    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_llm_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_embedding_dimensions: int = 1536

    llm_provider: str = "openai"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()


def get_memory_settings() -> MemorySettings:
    """Create MemorySettings from environment."""
    # The neo4j-agent-memory OpenAIEmbedder uses AsyncOpenAI under the hood.
    # For Azure OpenAI embeddings, we pass the API key and let the product
    # search fall back to text search if vector search fails. Full Azure
    # embedding support will be addressed when the agent is wired up.
    api_key = settings.openai_api_key or settings.azure_openai_api_key

    embedding_config: dict[str, Any] = {
        "provider": "openai",
        "model": settings.azure_openai_embedding_deployment or "text-embedding-3-small",
        "dimensions": settings.azure_openai_embedding_dimensions,
    }
    if api_key:
        embedding_config["api_key"] = SecretStr(api_key)

    return MemorySettings(
        neo4j={
            "uri": settings.neo4j_uri,
            "username": settings.neo4j_username,
            "password": SecretStr(settings.neo4j_password),
        },
        embedding=embedding_config,
    )


# --- Global State ---

memory_client: MemoryClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global memory_client

    logger.info("Connecting to Neo4j...")
    memory_client = MemoryClient(get_memory_settings())
    await memory_client.connect()
    logger.info("Connected to Neo4j")

    yield

    if memory_client:
        await memory_client.close()
        logger.info("Disconnected from Neo4j")


# --- App ---

app = FastAPI(
    title="Smart Shopping Assistant API",
    description="Retail assistant powered by LangGraph and Neo4j Agent Memory",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(description="User message text")
    session_id: str | None = Field(default=None, description="Existing session ID")
    user_id: str | None = Field(default=None, description="User identifier")


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    response: str
    session_id: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "degraded"]
    database: Literal["connected", "disconnected"]


class ProductItem(BaseModel):
    """Single product in search results."""

    id: str
    name: str
    description: str = ""
    price: float = 0.0
    category: str = ""
    brand: str = ""
    in_stock: bool = True
    score: float = 1.0


class ProductSearchResponse(BaseModel):
    """Product search response."""

    products: list[ProductItem]
    total: int = Field(ge=0)


class ProductDetailResponse(BaseModel):
    """Full product detail response."""

    id: str
    name: str
    description: str = ""
    price: float = 0.0
    category: str = ""
    brand: str = ""
    in_stock: bool = True
    inventory: int = 0
    image_url: str | None = None


class RelatedProductItem(BaseModel, extra="allow"):
    """A related product with connection info."""

    id: str
    name: str
    description: str = ""
    price: float = 0.0
    category: str = ""
    brand: str = ""


class RelatedProductsResponse(BaseModel):
    """Related products response."""

    related_products: list[RelatedProductItem]


class MemoryContextResponse(BaseModel):
    """Memory context for the current session."""

    history: str = Field(default="", description="Formatted conversation history")
    context: str = Field(default="", description="Long-term entity and fact context")
    preferences: list[dict[str, str]] = Field(
        default_factory=list, description="Matched user preferences"
    )
    similar_tasks: str = Field(default="", description="Formatted reasoning traces")


class GraphNodeResponse(BaseModel):
    """A node in the memory graph."""

    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelationshipResponse(BaseModel):
    """A relationship in the memory graph."""

    id: str
    type: str
    from_node: str
    to_node: str
    properties: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphResponse(BaseModel):
    """Memory graph for visualization."""

    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    relationships: list[GraphRelationshipResponse] = Field(default_factory=list)


class PreferenceItem(BaseModel):
    """A single user preference."""

    category: str
    preference: str
    context: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PreferencesResponse(BaseModel):
    """User preferences response."""

    preferences: list[PreferenceItem] = Field(default_factory=list)


# --- Session Management ---


class Session(BaseModel):
    """Tracked session."""

    user_id: str | None = None
    created_at: datetime


sessions: dict[str, Session] = {}


def get_or_create_session(session_id: str | None, user_id: str | None = None) -> str:
    """Get existing session or create new one."""
    if session_id and session_id in sessions:
        return session_id

    new_session_id = session_id or str(uuid4())
    sessions[new_session_id] = Session(
        user_id=user_id,
        created_at=datetime.now(UTC),
    )
    return new_session_id


# --- Chat Endpoints (placeholders until agent is wired up) ---


@app.post("/chat")
async def chat_stream(request: ChatRequest):
    """Chat endpoint with SSE streaming. Currently returns a placeholder response."""
    session_id = get_or_create_session(request.session_id, request.user_id)

    async def event_generator():
        yield {
            "event": "token",
            "data": json.dumps({
                "content": f"[placeholder] I received your message: '{request.message}'. "
                "The agent is not yet connected. This will be replaced in Phase 7."
            }),
        }
        yield {"event": "done", "data": json.dumps({"session_id": session_id})}

    return EventSourceResponse(event_generator())


@app.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """Non-streaming chat endpoint. Currently returns a placeholder response."""
    session_id = get_or_create_session(request.session_id, request.user_id)

    return ChatResponse(
        response=f"[placeholder] I received your message: '{request.message}'. "
        "The agent is not yet connected. This will be replaced in Phase 7.",
        session_id=session_id,
    )


# --- Memory Endpoints ---


def _get_agent_memory(session_id: str) -> Neo4jAgentMemory:
    """Create a Neo4jAgentMemory bound to a session."""
    return Neo4jAgentMemory(
        memory_client=_get_client(),
        session_id=session_id,
        include_short_term=True,
        include_long_term=True,
        include_reasoning=True,
    )


@app.get("/memory/context", response_model=MemoryContextResponse)
async def get_memory_context(
    session_id: str = Query(..., description="Session ID"),
    query: str = Query("", description="Query for relevant context"),
) -> MemoryContextResponse:
    """Get current memory context for a session."""
    try:
        memory = _get_agent_memory(session_id)
        result = await memory._load_memory_variables_async({"input": query})
        return MemoryContextResponse(
            history=result.get("history", ""),
            context=result.get("context", ""),
            preferences=result.get("preferences", []),
            similar_tasks=result.get("similar_tasks", ""),
        )
    except Exception as e:
        logger.exception("Error loading memory context")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/graph", response_model=MemoryGraphResponse)
async def get_memory_graph(
    session_id: str = Query(..., description="Session ID"),
    center_entity: str | None = Query(None, description="Center entity for graph"),
    max_hops: int = Query(2, ge=1, le=5, description="Maximum relationship hops"),
) -> MemoryGraphResponse:
    """Get memory graph for visualization."""
    try:
        client = _get_client()
        graph = await client.get_graph(session_id=session_id)
        nodes = [
            GraphNodeResponse(id=n.id, labels=n.labels, properties=n.properties)
            for n in graph.nodes
        ]
        relationships = [
            GraphRelationshipResponse(
                id=r.id, type=r.type, from_node=r.from_node,
                to_node=r.to_node, properties=r.properties,
            )
            for r in graph.relationships
        ]
        return MemoryGraphResponse(nodes=nodes, relationships=relationships)
    except Exception as e:
        logger.exception("Error loading memory graph")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/preferences", response_model=PreferencesResponse)
async def get_preferences(
    session_id: str = Query(..., description="Session ID"),
    category: str | None = Query(None, description="Filter by category"),
) -> PreferencesResponse:
    """Get learned user preferences."""
    try:
        client = _get_client()
        prefs = await client.long_term.search_preferences(
            query=category or "",
            category=category,
            limit=20,
        )
        items = [
            PreferenceItem(
                category=p.category,
                preference=p.preference,
                context=p.context,
                confidence=p.confidence,
            )
            for p in prefs
        ]
        return PreferencesResponse(preferences=items)
    except Exception as e:
        logger.exception("Error loading preferences")
        raise HTTPException(status_code=500, detail=str(e))


# --- Product Endpoints (fully functional, query Neo4j directly) ---


def _get_client() -> MemoryClient:
    """Get the memory client or raise 503."""
    if not memory_client or not memory_client.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")
    return memory_client


def _db() -> Any:
    """Get the Neo4j graph client for direct Cypher queries."""
    return _get_client().graph


# NOTE: MemoryClient does not expose a public embedder property.
# Accessing _embedder is the only way to get the embedding provider.
def _embedder() -> Any:
    """Get the embedding provider."""
    return _get_client()._embedder


@app.get("/products/search", response_model=ProductSearchResponse)
async def search_products(
    query: str = Query(..., description="Search query"),
    category: str | None = Query(None, description="Filter by category"),
    brand: str | None = Query(None, description="Filter by brand"),
    max_price: float | None = Query(None, ge=0, description="Maximum price"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
) -> ProductSearchResponse:
    """Search product catalog using vector similarity with text fallback."""
    conditions = ["p:Product"]
    params: dict[str, Any] = {"query": query, "limit": limit}

    if category:
        conditions.append("p.category = $category")
        params["category"] = category
    if brand:
        conditions.append("p.brand = $brand")
        params["brand"] = brand
    if max_price is not None:
        conditions.append("p.price <= $max_price")
        params["max_price"] = max_price

    where_clause = " AND ".join(conditions)

    try:
        embedding = await _embedder().embed(query)
        params["embedding"] = embedding

        cypher = f"""
        CALL db.index.vector.queryNodes('product_embedding', $limit, $embedding)
        YIELD node as p, score
        WHERE {where_clause}
        RETURN elementId(p) AS id, p.name AS name,
               coalesce(p.description, '') AS description,
               coalesce(p.price, 0) AS price,
               coalesce(p.category, '') AS category,
               coalesce(p.brand, '') AS brand,
               coalesce(p.in_stock, true) AS in_stock,
               score
        ORDER BY score DESC
        """

        result = await _db().execute_read(cypher, params)
        products = [ProductItem.model_validate(dict(r)) for r in result]
        return ProductSearchResponse(products=products, total=len(products))

    except Exception:
        logger.exception("Vector search failed, falling back to text search")
        try:
            cypher = """
            MATCH (p:Product)
            WHERE p.name CONTAINS $query OR p.description CONTAINS $query
            RETURN elementId(p) AS id, p.name AS name,
                   coalesce(p.description, '') AS description,
                   coalesce(p.price, 0) AS price,
                   coalesce(p.category, '') AS category,
                   coalesce(p.brand, '') AS brand,
                   coalesce(p.in_stock, true) AS in_stock
            LIMIT $limit
            """
            result = await _db().execute_read(cypher, {"query": query, "limit": limit})
            products = [
                ProductItem.model_validate({**dict(r), "score": 1.0})
                for r in result
            ]
            return ProductSearchResponse(products=products, total=len(products))

        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=str(fallback_error))


@app.get("/products/{product_id}", response_model=ProductDetailResponse)
async def get_product(product_id: str) -> ProductDetailResponse:
    """Get product details by ID."""
    cypher = """
    MATCH (p:Product)
    WHERE elementId(p) = $product_id OR p.id = $product_id
    OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
    OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand)
    RETURN elementId(p) AS id, p.name AS name,
           coalesce(p.description, '') AS description,
           coalesce(p.price, 0) AS price,
           coalesce(c.name, p.category, '') AS category,
           coalesce(b.name, p.brand, '') AS brand,
           coalesce(p.in_stock, true) AS in_stock,
           coalesce(p.inventory, 0) AS inventory,
           p.image_url AS image_url
    """

    try:
        result = await _db().execute_read(cypher, {"product_id": product_id})
        if not result:
            raise HTTPException(status_code=404, detail="Product not found")
        return ProductDetailResponse.model_validate(dict(result[0]))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting product")
        raise HTTPException(status_code=500, detail=str(e))


ALLOWED_RELATIONSHIP_TYPES = frozenset({
    "IN_CATEGORY", "MADE_BY", "HAS_ATTRIBUTE", "BOUGHT_TOGETHER", "SIMILAR_TO",
})


@app.get("/products/{product_id}/related", response_model=RelatedProductsResponse)
async def get_related_products(
    product_id: str,
    limit: int = Query(5, ge=1, le=50, description="Maximum results"),
    relationship_type: str | None = Query(None, description="Filter by relationship"),
) -> RelatedProductsResponse:
    """Get products related to a given product."""
    if relationship_type and relationship_type not in ALLOWED_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship_type. Allowed: {sorted(ALLOWED_RELATIONSHIP_TYPES)}",
        )

    if relationship_type:
        cypher = f"""
        MATCH (p:Product)-[:{relationship_type}]->(shared)<-[:{relationship_type}]-(related:Product)
        WHERE (elementId(p) = $product_id OR p.id = $product_id)
        AND related <> p
        RETURN elementId(related) AS id, related.name AS name,
               coalesce(related.description, '')[..100] AS description,
               coalesce(related.price, 0) AS price,
               coalesce(related.category, '') AS category,
               coalesce(related.brand, '') AS brand,
               count(shared) AS shared_count
        ORDER BY shared_count DESC
        LIMIT $limit
        """
    else:
        cypher = """
        MATCH (p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        CALL (p) {
            MATCH (p)-[:IN_CATEGORY]->(c)<-[:IN_CATEGORY]-(related:Product)
            WHERE related <> p
            RETURN related, 'category' as relation_type, c.name as shared
            UNION
            MATCH (p)-[:MADE_BY]->(b)<-[:MADE_BY]-(related:Product)
            WHERE related <> p
            RETURN related, 'brand' as relation_type, b.name as shared
            UNION
            MATCH (p)-[:HAS_ATTRIBUTE]->(a)<-[:HAS_ATTRIBUTE]-(related:Product)
            WHERE related <> p
            RETURN related, 'attribute' as relation_type, a.name as shared
        }
        WITH related,
             collect(DISTINCT {type: relation_type, value: shared}) AS connections
        RETURN elementId(related) AS id, related.name AS name,
               coalesce(related.description, '')[..100] AS description,
               coalesce(related.price, 0) AS price,
               coalesce(related.category, '') AS category,
               coalesce(related.brand, '') AS brand,
               connections
        LIMIT $limit
        """

    try:
        result = await _db().execute_read(
            cypher, {"product_id": product_id, "limit": limit}
        )
        related = [RelatedProductItem.model_validate(dict(r)) for r in result]
        return RelatedProductsResponse(related_products=related)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting related products")
        raise HTTPException(status_code=500, detail=str(e))


# --- Health Check ---


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    db_connected = memory_client is not None and memory_client.is_connected

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        database="connected" if db_connected else "disconnected",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
