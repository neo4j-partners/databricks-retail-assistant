"""Shared constants for the retail assistant backend."""

ALLOWED_RELATIONSHIP_TYPES = frozenset({
    "IN_CATEGORY",
    "MADE_BY",
    "HAS_ATTRIBUTE",
    "BOUGHT_TOGETHER",
    "SIMILAR_TO",
})

TAX_RATE = 0.08
