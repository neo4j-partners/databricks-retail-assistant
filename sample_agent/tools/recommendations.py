"""Recommendation tools for the LangGraph retail agent.

Provides personalized product recommendations using graph relationships,
user preferences, and collaborative filtering patterns.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from neo4j_agent_memory import MemoryClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------


class RecommendationsInput(BaseModel):
    """Input for getting personalized recommendations."""

    category: str | None = Field(default=None, description="Product category to recommend from")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of recommendations")
    session_id: str | None = Field(default=None, description="Session ID for personalization context")


class BoughtTogetherInput(BaseModel):
    """Input for finding frequently co-purchased products."""

    product_id: str = Field(description="The product ID to find co-purchased items for")
    limit: int = Field(default=3, ge=1, le=10, description="Maximum number of results")


class ConnectionInput(BaseModel):
    """Input for explaining the connection between two products."""

    product_id_a: str = Field(description="First product ID")
    product_id_b: str = Field(description="Second product ID")


# ---------------------------------------------------------------------------
# Tool Factories
# ---------------------------------------------------------------------------


def create_recommendation_tools(client: MemoryClient) -> list[BaseTool]:
    """Create recommendation tools bound to the given MemoryClient."""

    @tool(args_schema=RecommendationsInput)
    async def get_recommendations(
        category: str | None = None,
        limit: int = 5,
        session_id: str | None = None,
    ) -> str:
        """Get personalized product recommendations. Uses graph relationships and user preferences to suggest relevant products."""
        params: dict[str, Any] = {"limit": limit}

        # Try preference-based recommendations first if session context exists
        if session_id:
            try:
                prefs = await client.long_term.search_preferences(
                    query=category or "product preferences",
                    limit=5,
                )
                if prefs:
                    pref_terms = [p.preference for p in prefs]
                    params["pref_terms"] = pref_terms

                    cypher = """
                    UNWIND $pref_terms AS term
                    MATCH (p:Product)
                    WHERE p.name CONTAINS term
                       OR p.description CONTAINS term
                       OR p.brand CONTAINS term
                       OR p.category CONTAINS term
                    WITH DISTINCT p, count(*) AS match_count
                    RETURN elementId(p) AS id, p.name AS name,
                           coalesce(p.description, '') AS description,
                           coalesce(p.price, 0) AS price,
                           coalesce(p.category, '') AS category,
                           coalesce(p.brand, '') AS brand,
                           coalesce(p.in_stock, true) AS in_stock,
                           match_count AS relevance
                    ORDER BY match_count DESC
                    LIMIT $limit
                    """
                    result = await client.graph.execute_read(cypher, params)
                    if result:
                        products = [dict(r) for r in result]
                        return json.dumps({
                            "recommendations": products,
                            "personalized": True,
                            "based_on": [p.preference for p in prefs],
                        })
            except Exception:
                logger.info("Preference-based recommendations unavailable, using graph fallback")

        # Fallback: popular products by graph connectivity
        category_filter = "AND p.category = $category" if category else ""
        if category:
            params["category"] = category

        cypher = f"""
        MATCH (p:Product)
        WHERE p.in_stock = true {category_filter}
        OPTIONAL MATCH (p)-[r]-()
        WITH p, count(r) AS connections
        RETURN elementId(p) AS id, p.name AS name,
               coalesce(p.description, '') AS description,
               coalesce(p.price, 0) AS price,
               coalesce(p.category, '') AS category,
               coalesce(p.brand, '') AS brand,
               connections AS relevance
        ORDER BY connections DESC
        LIMIT $limit
        """
        result = await client.graph.execute_read(cypher, params)
        products = [dict(r) for r in result]
        return json.dumps({
            "recommendations": products,
            "personalized": False,
            "based_on": ["popularity"],
        })

    @tool(args_schema=BoughtTogetherInput)
    async def get_bought_together(product_id: str, limit: int = 3) -> str:
        """Find products that are frequently bought together with a given product. Use this for cross-sell suggestions."""
        cypher = """
        MATCH (p:Product)-[r:BOUGHT_TOGETHER]-(related:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        RETURN elementId(related) AS id, related.name AS name,
               coalesce(related.description, '') AS description,
               coalesce(related.price, 0) AS price,
               coalesce(related.category, '') AS category,
               coalesce(related.brand, '') AS brand,
               coalesce(r.frequency, 0) AS purchase_frequency,
               coalesce(r.confidence, 0.0) AS confidence
        ORDER BY purchase_frequency DESC
        LIMIT $limit
        """
        result = await client.graph.execute_read(
            cypher, {"product_id": product_id, "limit": limit}
        )
        items = [dict(r) for r in result]
        return json.dumps({
            "source_product_id": product_id,
            "frequently_bought_together": items,
        })

    @tool(args_schema=ConnectionInput)
    async def explain_product_connection(product_id_a: str, product_id_b: str) -> str:
        """Explain how two products are related through the product graph. Use this when a customer asks why two products are recommended together."""
        # Find shared attributes between the two products
        cypher = """
        MATCH (a:Product), (b:Product)
        WHERE (elementId(a) = $id_a OR a.id = $id_a)
          AND (elementId(b) = $id_b OR b.id = $id_b)
        OPTIONAL MATCH (a)-[:IN_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(b)
        OPTIONAL MATCH (a)-[:MADE_BY]->(br:Brand)<-[:MADE_BY]-(b)
        OPTIONAL MATCH (a)-[:HAS_ATTRIBUTE]->(attr)<-[:HAS_ATTRIBUTE]-(b)
        RETURN a.name AS product_a, b.name AS product_b,
               collect(DISTINCT c.name) AS shared_categories,
               collect(DISTINCT br.name) AS shared_brands,
               collect(DISTINCT attr.name) AS shared_attributes
        """
        result = await client.graph.execute_read(
            cypher, {"id_a": product_id_a, "id_b": product_id_b}
        )

        if not result:
            return json.dumps({
                "connected": False,
                "explanation": "Could not find one or both products.",
            })

        row = dict(result[0])
        shared_categories = [c for c in row.get("shared_categories", []) if c]
        shared_brands = [b for b in row.get("shared_brands", []) if b]
        shared_attributes = [a for a in row.get("shared_attributes", []) if a]

        connections: list[str] = []
        if shared_categories:
            connections.append(f"same category: {', '.join(shared_categories)}")
        if shared_brands:
            connections.append(f"same brand: {', '.join(shared_brands)}")
        if shared_attributes:
            connections.append(f"shared attributes: {', '.join(shared_attributes)}")

        connected = bool(connections)
        explanation = (
            f"{row['product_a']} and {row['product_b']} are connected through: {'; '.join(connections)}"
            if connected
            else f"{row['product_a']} and {row['product_b']} have no direct graph connections."
        )

        return json.dumps({
            "connected": connected,
            "product_a": row["product_a"],
            "product_b": row["product_b"],
            "shared_categories": shared_categories,
            "shared_brands": shared_brands,
            "shared_attributes": shared_attributes,
            "explanation": explanation,
        })

    return [get_recommendations, get_bought_together, explain_product_connection]
