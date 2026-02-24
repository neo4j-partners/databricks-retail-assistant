"""Product-related response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    """Shared fields across product representations."""

    id: str
    name: str
    description: str = ""
    price: float = Field(default=0.0, ge=0)
    category: str = ""
    brand: str = ""
    in_stock: bool = True


class ProductItem(ProductBase):
    """Single product in search results."""

    score: float = Field(default=1.0, ge=0.0, le=1.0)


class ProductSearchResponse(BaseModel):
    """Product search response."""

    products: list[ProductItem]
    total: int = Field(ge=0)


class ProductDetailResponse(ProductBase):
    """Full product detail response."""

    inventory: int = 0
    image_url: str | None = None


class RelatedProductItem(ProductBase):
    """A related product with connection info."""

    model_config = ConfigDict(extra="allow")


class RelatedProductsResponse(BaseModel):
    """Related products response."""

    related_products: list[RelatedProductItem]
