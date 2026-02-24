"""Product search and detail tools for the LangGraph retail agent.

Each tool is created via a factory function that closes over the MemoryClient,
keeping tool definitions free of global state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from neo4j_agent_memory import MemoryClient

from sample_agent.constants import ALLOWED_RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------


class SearchProductsInput(BaseModel):
    """Input for searching the product catalog."""

    query: str = Field(description="Search query describing what the customer is looking for")
    category: str | None = Field(default=None, description="Filter by product category")
    brand: str | None = Field(default=None, description="Filter by brand name")
    max_price: float | None = Field(default=None, ge=0, description="Maximum price filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of results")


class ProductDetailsInput(BaseModel):
    """Input for getting product details."""

    product_id: str = Field(description="The product ID to look up")


class RelatedProductsInput(BaseModel):
    """Input for finding related products."""

    product_id: str = Field(description="The product ID to find related products for")
    relationship_type: str | None = Field(
        default=None,
        description="Filter by relationship type: IN_CATEGORY, MADE_BY, HAS_ATTRIBUTE, BOUGHT_TOGETHER, SIMILAR_TO",
    )
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of related products")


# ---------------------------------------------------------------------------
# Tool Factories
# ---------------------------------------------------------------------------


def create_product_search_tools(client: MemoryClient) -> list[BaseTool]:
    """Create product search tools bound to the given MemoryClient."""

    @tool(args_schema=SearchProductsInput)
    async def search_products(
        query: str,
        category: str | None = None,
        brand: str | None = None,
        max_price: float | None = None,
        limit: int = 10,
    ) -> str:
        """Search the product catalog by query. Use this when a customer asks about products, wants to browse, or is looking for something specific."""
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
            # NOTE: MemoryClient does not expose a public embedder property.
            # Accessing _embedder is the only way to get the embedding provider.
            embedding = await client._embedder.embed(query)
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
            result = await client.graph.execute_read(cypher, params)
        except Exception:
            logger.info("Vector search unavailable, falling back to text search")
            cypher = """
            MATCH (p:Product)
            WHERE p.name CONTAINS $query OR p.description CONTAINS $query
            RETURN elementId(p) AS id, p.name AS name,
                   coalesce(p.description, '') AS description,
                   coalesce(p.price, 0) AS price,
                   coalesce(p.category, '') AS category,
                   coalesce(p.brand, '') AS brand,
                   coalesce(p.in_stock, true) AS in_stock,
                   1.0 AS score
            LIMIT $limit
            """
            result = await client.graph.execute_read(cypher, {"query": query, "limit": limit})

        products = [dict(r) for r in result]
        return json.dumps({"products": products, "count": len(products)})

    @tool(args_schema=ProductDetailsInput)
    async def get_product_details(product_id: str) -> str:
        """Get full details for a specific product by ID. Use this when the customer wants to know more about a particular product."""
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
        result = await client.graph.execute_read(cypher, {"product_id": product_id})
        if not result:
            return json.dumps({"error": "Product not found", "product_id": product_id})
        return json.dumps(dict(result[0]))

    @tool(args_schema=RelatedProductsInput)
    async def get_related_products(
        product_id: str,
        relationship_type: str | None = None,
        limit: int = 5,
    ) -> str:
        """Find products related to a given product through graph relationships. Use this for recommendations like 'what goes well with this' or 'similar items'."""
        if relationship_type and relationship_type not in ALLOWED_RELATIONSHIP_TYPES:
            return json.dumps({
                "error": f"Invalid relationship_type. Allowed: {sorted(ALLOWED_RELATIONSHIP_TYPES)}"
            })

        params: dict[str, Any] = {"product_id": product_id, "limit": limit}

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
                   size(connections) AS relevance_score
            ORDER BY relevance_score DESC
            LIMIT $limit
            """

        result = await client.graph.execute_read(cypher, params)
        related = [dict(r) for r in result]
        return json.dumps({"source_product_id": product_id, "related_products": related})

    return [search_products, get_product_details, get_related_products]
