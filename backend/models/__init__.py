"""Pydantic request/response models for the retail assistant API."""

from backend.models.chat import ChatRequest, ChatResponse
from backend.models.health import HealthResponse
from backend.models.memory import (
    GraphNodeResponse,
    GraphRelationshipResponse,
    MemoryContextResponse,
    MemoryGraphResponse,
    PreferenceItem,
    PreferencesResponse,
)
from backend.models.products import (
    ProductBase,
    ProductDetailResponse,
    ProductItem,
    ProductSearchResponse,
    RelatedProductItem,
    RelatedProductsResponse,
)
from backend.models.session import Session

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "GraphNodeResponse",
    "GraphRelationshipResponse",
    "HealthResponse",
    "MemoryContextResponse",
    "MemoryGraphResponse",
    "PreferenceItem",
    "PreferencesResponse",
    "ProductBase",
    "ProductDetailResponse",
    "ProductItem",
    "ProductSearchResponse",
    "RelatedProductItem",
    "RelatedProductsResponse",
    "Session",
]
