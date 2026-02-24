"""Inventory tools for the LangGraph retail agent.

Provides stock checking and alternative product finding capabilities.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from neo4j_agent_memory import MemoryClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------


class InventoryCheckInput(BaseModel):
    """Input for checking product inventory."""

    product_id: str = Field(description="The product ID to check stock for")


class AlternativesInput(BaseModel):
    """Input for finding in-stock alternatives."""

    product_id: str = Field(description="The out-of-stock product ID to find alternatives for")
    max_results: int = Field(default=3, ge=1, le=10, description="Maximum number of alternatives")


# ---------------------------------------------------------------------------
# Tool Factories
# ---------------------------------------------------------------------------


def create_inventory_tools(client: MemoryClient) -> list[BaseTool]:
    """Create inventory tools bound to the given MemoryClient."""

    @tool(args_schema=InventoryCheckInput)
    async def check_inventory(product_id: str) -> str:
        """Check the stock status and quantity for a product. Use this before confirming availability to a customer."""
        cypher = """
        MATCH (p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        RETURN elementId(p) AS id, p.name AS name,
               coalesce(p.in_stock, false) AS in_stock,
               coalesce(p.inventory, 0) AS quantity,
               p.restock_date AS restock_date
        """
        result = await client.graph.execute_read(cypher, {"product_id": product_id})

        if not result:
            return json.dumps({"error": "Product not found", "product_id": product_id})

        row = dict(result[0])
        quantity = row["quantity"]

        if not row["in_stock"] or quantity == 0:
            status = "out_of_stock"
            message = f"{row['name']} is currently out of stock."
            if row.get("restock_date"):
                message += f" Expected restock: {row['restock_date']}."
        elif quantity <= 5:
            status = "low_stock"
            message = f"{row['name']} is in stock but running low ({quantity} remaining)."
        else:
            status = "in_stock"
            message = f"{row['name']} is in stock ({quantity} available)."

        return json.dumps({
            "product_id": row["id"],
            "name": row["name"],
            "status": status,
            "quantity": quantity,
            "in_stock": row["in_stock"],
            "message": message,
        })

    @tool(args_schema=AlternativesInput)
    async def find_alternatives(product_id: str, max_results: int = 3) -> str:
        """Find in-stock alternatives for a product. Use this when a product is out of stock to suggest substitutes in the same category and similar price range."""
        # Get the original product's details for matching
        cypher = """
        MATCH (p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        RETURN p.name AS name, p.category AS category,
               p.brand AS brand, coalesce(p.price, 0) AS price
        """
        result = await client.graph.execute_read(cypher, {"product_id": product_id})

        if not result:
            return json.dumps({"error": "Product not found", "product_id": product_id})

        original = dict(result[0])
        price = original["price"]
        price_min = price * 0.7
        price_max = price * 1.3

        # Find alternatives: same category, similar price, in stock
        cypher = """
        MATCH (alt:Product)
        WHERE alt.in_stock = true
          AND alt.category = $category
          AND alt.price >= $price_min
          AND alt.price <= $price_max
          AND NOT (elementId(alt) = $product_id OR alt.id = $product_id)
        RETURN elementId(alt) AS id, alt.name AS name,
               coalesce(alt.description, '') AS description,
               coalesce(alt.price, 0) AS price,
               coalesce(alt.category, '') AS category,
               coalesce(alt.brand, '') AS brand,
               coalesce(alt.inventory, 0) AS quantity,
               'same category, similar price' AS reason
        ORDER BY abs(alt.price - $target_price) ASC
        LIMIT $limit
        """
        result = await client.graph.execute_read(cypher, {
            "product_id": product_id,
            "category": original["category"],
            "price_min": price_min,
            "price_max": price_max,
            "target_price": price,
            "limit": max_results,
        })

        alternatives = [dict(r) for r in result]
        return json.dumps({
            "original_product": original["name"],
            "original_product_id": product_id,
            "alternatives": alternatives,
            "found": len(alternatives) > 0,
        })

    return [check_inventory, find_alternatives]
