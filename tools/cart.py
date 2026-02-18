"""Shopping cart tools for the LangGraph retail agent.

Manages a session-based shopping cart stored in Neo4j with Cart and CONTAINS
relationship nodes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from neo4j_agent_memory import MemoryClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------


class CartInput(BaseModel):
    """Input for viewing or clearing the cart."""

    session_id: str = Field(description="The session ID that owns the cart")


class AddToCartInput(BaseModel):
    """Input for adding a product to the cart."""

    session_id: str = Field(description="The session ID that owns the cart")
    product_id: str = Field(description="The product ID to add")
    quantity: int = Field(default=1, ge=1, description="Number of units to add")


class RemoveFromCartInput(BaseModel):
    """Input for removing a product from the cart."""

    session_id: str = Field(description="The session ID that owns the cart")
    product_id: str = Field(description="The product ID to remove")


class UpdateCartInput(BaseModel):
    """Input for updating a cart item quantity."""

    session_id: str = Field(description="The session ID that owns the cart")
    product_id: str = Field(description="The product ID to update")
    quantity: int = Field(ge=0, description="New quantity (0 to remove)")


class CouponInput(BaseModel):
    """Input for applying a coupon code."""

    session_id: str = Field(description="The session ID that owns the cart")
    coupon_code: str = Field(description="The coupon code to apply")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_cart_contents(client: MemoryClient, session_id: str) -> dict[str, Any]:
    """Fetch current cart contents and compute totals."""
    cypher = """
    MATCH (cart:Cart {session_id: $session_id})-[r:CONTAINS]->(p:Product)
    RETURN elementId(p) AS id, p.name AS name,
           coalesce(p.price, 0) AS price,
           r.quantity AS quantity,
           coalesce(p.price, 0) * r.quantity AS line_total
    """
    result = await client.graph.execute_read(cypher, {"session_id": session_id})

    items = [dict(r) for r in result]
    subtotal = sum(item["line_total"] for item in items)
    tax = round(subtotal * 0.08, 2)

    return {
        "session_id": session_id,
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "subtotal": round(subtotal, 2),
        "estimated_tax": tax,
        "total": round(subtotal + tax, 2),
    }


# ---------------------------------------------------------------------------
# Tool Factories
# ---------------------------------------------------------------------------


async def _remove_item(client: MemoryClient, session_id: str, product_id: str) -> dict[str, Any]:
    """Remove a single item from the cart. Shared by remove_from_cart and update_cart_item."""
    cypher = """
    MATCH (cart:Cart {session_id: $session_id})-[r:CONTAINS]->(p:Product)
    WHERE elementId(p) = $product_id OR p.id = $product_id
    DELETE r
    RETURN p.name AS name
    """
    result = await client.graph.execute_write(cypher, {
        "session_id": session_id,
        "product_id": product_id,
    })
    if not result:
        return {"success": False, "message": "Item not found in cart."}
    return {
        "success": True,
        "message": f"Removed {result[0]['name']} from cart.",
        "product_name": result[0]["name"],
    }


def create_cart_tools(client: MemoryClient) -> list:
    """Create shopping cart tools bound to the given MemoryClient."""

    @tool(args_schema=CartInput)
    async def get_cart(session_id: str) -> str:
        """Get the current shopping cart contents including items, quantities, and totals. Use this when the customer asks about their cart."""
        cart = await _get_cart_contents(client, session_id)
        return json.dumps(cart)

    @tool(args_schema=AddToCartInput)
    async def add_to_cart(session_id: str, product_id: str, quantity: int = 1) -> str:
        """Add a product to the shopping cart. Checks that the product exists and is in stock before adding."""
        # Verify product exists and is in stock
        check_cypher = """
        MATCH (p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        RETURN p.name AS name, coalesce(p.in_stock, false) AS in_stock,
               coalesce(p.inventory, 0) AS inventory, coalesce(p.price, 0) AS price
        """
        result = await client.graph.execute_read(check_cypher, {"product_id": product_id})
        if not result:
            return json.dumps({"success": False, "message": "Product not found."})

        product = dict(result[0])
        if not product["in_stock"]:
            return json.dumps({
                "success": False,
                "message": f"{product['name']} is out of stock.",
            })
        if product["inventory"] < quantity:
            return json.dumps({
                "success": False,
                "message": f"Only {product['inventory']} units of {product['name']} available.",
            })

        # Add to cart (merge to handle existing items)
        add_cypher = """
        MERGE (cart:Cart {session_id: $session_id})
        WITH cart
        MATCH (p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        MERGE (cart)-[r:CONTAINS]->(p)
        ON CREATE SET r.quantity = $quantity
        ON MATCH SET r.quantity = r.quantity + $quantity
        RETURN r.quantity AS quantity_in_cart
        """
        result = await client.graph.execute_write(add_cypher, {
            "session_id": session_id,
            "product_id": product_id,
            "quantity": quantity,
        })

        qty_in_cart = result[0]["quantity_in_cart"] if result else quantity
        return json.dumps({
            "success": True,
            "message": f"Added {quantity} x {product['name']} to cart.",
            "product_name": product["name"],
            "quantity_in_cart": qty_in_cart,
            "line_total": round(product["price"] * qty_in_cart, 2),
        })

    @tool(args_schema=RemoveFromCartInput)
    async def remove_from_cart(session_id: str, product_id: str) -> str:
        """Remove a product from the shopping cart entirely."""
        result = await _remove_item(client, session_id, product_id)
        return json.dumps(result)

    @tool(args_schema=UpdateCartInput)
    async def update_cart_item(session_id: str, product_id: str, quantity: int) -> str:
        """Update the quantity of an item in the cart. Set quantity to 0 to remove the item."""
        if quantity == 0:
            result = await _remove_item(client, session_id, product_id)
            return json.dumps(result)

        cypher = """
        MATCH (cart:Cart {session_id: $session_id})-[r:CONTAINS]->(p:Product)
        WHERE elementId(p) = $product_id OR p.id = $product_id
        SET r.quantity = $quantity
        RETURN p.name AS name, coalesce(p.price, 0) AS price, r.quantity AS quantity
        """
        result = await client.graph.execute_write(cypher, {
            "session_id": session_id,
            "product_id": product_id,
            "quantity": quantity,
        })

        if not result:
            return json.dumps({"success": False, "message": "Item not found in cart."})

        row = dict(result[0])
        return json.dumps({
            "success": True,
            "message": f"Updated {row['name']} quantity to {quantity}.",
            "product_name": row["name"],
            "quantity": quantity,
            "line_total": round(row["price"] * quantity, 2),
        })

    @tool(args_schema=CartInput)
    async def clear_cart(session_id: str) -> str:
        """Remove all items from the shopping cart."""
        cypher = """
        MATCH (cart:Cart {session_id: $session_id})-[r:CONTAINS]->()
        WITH cart, collect(r) AS rels
        FOREACH (r IN rels | DELETE r)
        RETURN size(rels) AS items_removed
        """
        result = await client.graph.execute_write(cypher, {"session_id": session_id})
        removed = result[0]["items_removed"] if result else 0

        return json.dumps({
            "success": True,
            "message": f"Cart cleared. Removed {removed} item(s).",
            "items_removed": removed,
        })

    @tool(args_schema=CouponInput)
    async def apply_coupon(session_id: str, coupon_code: str) -> str:
        """Apply a coupon code to the shopping cart for a discount."""
        # Validate coupon
        coupon_cypher = """
        MATCH (c:Coupon {code: $code})
        WHERE c.active = true
        RETURN c.code AS code, c.discount_type AS discount_type,
               c.discount_value AS discount_value,
               coalesce(c.min_purchase, 0) AS min_purchase
        """
        result = await client.graph.execute_read(coupon_cypher, {"code": coupon_code})

        if not result:
            return json.dumps({"success": False, "message": "Invalid or expired coupon code."})

        coupon = dict(result[0])
        cart = await _get_cart_contents(client, session_id)

        if cart["subtotal"] < coupon["min_purchase"]:
            return json.dumps({
                "success": False,
                "message": f"Minimum purchase of ${coupon['min_purchase']:.2f} required for this coupon.",
            })

        if coupon["discount_type"] == "percentage":
            discount = round(cart["subtotal"] * coupon["discount_value"] / 100, 2)
        else:
            discount = min(coupon["discount_value"], cart["subtotal"])

        # Apply discount to cart
        apply_cypher = """
        MERGE (cart:Cart {session_id: $session_id})
        SET cart.coupon_code = $code, cart.discount = $discount
        """
        await client.graph.execute_write(apply_cypher, {
            "session_id": session_id,
            "code": coupon_code,
            "discount": discount,
        })

        new_total = round(cart["subtotal"] - discount + cart["estimated_tax"], 2)
        return json.dumps({
            "success": True,
            "message": f"Coupon '{coupon_code}' applied! Discount: ${discount:.2f}.",
            "discount": discount,
            "new_total": new_total,
        })

    return [get_cart, add_to_cart, remove_from_cart, update_cart_item, clear_cart, apply_coupon]
