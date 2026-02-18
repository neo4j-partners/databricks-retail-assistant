"""Product search, detail, and related product endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.constants import ALLOWED_RELATIONSHIP_TYPES
from backend.dependencies import get_db, get_embedder
from backend.models.products import (
    ProductDetailResponse,
    ProductItem,
    ProductSearchResponse,
    RelatedProductItem,
    RelatedProductsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

Db = Annotated[Any, Depends(get_db)]
Embedder = Annotated[Any, Depends(get_embedder)]


@router.get("/search", response_model=ProductSearchResponse)
async def search_products(
    db: Db,
    embedder: Embedder,
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
        embedding = await embedder.embed(query)
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

        result = await db.execute_read(cypher, params)
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
            result = await db.execute_read(cypher, {"query": query, "limit": limit})
            products = [
                ProductItem.model_validate({**dict(r), "score": 1.0})
                for r in result
            ]
            return ProductSearchResponse(products=products, total=len(products))

        except Exception:
            logger.exception("Text search fallback also failed")
            raise HTTPException(status_code=500, detail="Product search failed")


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product(product_id: str, db: Db) -> ProductDetailResponse:
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
        result = await db.execute_read(cypher, {"product_id": product_id})
        if not result:
            raise HTTPException(status_code=404, detail="Product not found")
        return ProductDetailResponse.model_validate(dict(result[0]))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting product")
        raise HTTPException(status_code=500, detail="Failed to retrieve product")


@router.get("/{product_id}/related", response_model=RelatedProductsResponse)
async def get_related_products(
    product_id: str,
    db: Db,
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
        result = await db.execute_read(
            cypher, {"product_id": product_id, "limit": limit}
        )
        related = [RelatedProductItem.model_validate(dict(r)) for r in result]
        return RelatedProductsResponse(related_products=related)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting related products")
        raise HTTPException(status_code=500, detail="Failed to retrieve related products")
