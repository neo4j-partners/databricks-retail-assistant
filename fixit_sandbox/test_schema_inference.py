"""Verify that @tool without args_schema correctly infers schemas.

The fix removed explicit args_schema= from product tool decorators so that
LangChain infers schemas from function signatures.  ToolRuntime parameters
must be hidden from the LLM-facing schema (tool_call_schema) while all
user-facing parameters remain visible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# dbx_agent/ uses relative imports (flat MLflow packaging), so we add it
# to sys.path so `from context import RetailContext` resolves.
_dbx_dir = str(Path(__file__).resolve().parent.parent / "dbx_agent")
if _dbx_dir not in sys.path:
    sys.path.insert(0, _dbx_dir)

from product_search import search_products, get_product_details, get_related_products  # noqa: E402
from memory_tool import remember_message, recall_memory  # noqa: E402


# ── Product tools ────────────────────────────────────────────────────────


class TestSearchProductsSchema:
    def test_runtime_hidden_from_llm(self):
        fields = set(search_products.tool_call_schema.model_fields)
        assert "runtime" not in fields

    def test_user_params_present(self):
        fields = set(search_products.tool_call_schema.model_fields)
        assert fields == {"query", "category", "brand", "max_price", "limit"}


class TestGetProductDetailsSchema:
    def test_runtime_hidden_from_llm(self):
        fields = set(get_product_details.tool_call_schema.model_fields)
        assert "runtime" not in fields

    def test_user_params_present(self):
        fields = set(get_product_details.tool_call_schema.model_fields)
        assert fields == {"product_id"}


class TestGetRelatedProductsSchema:
    def test_runtime_hidden_from_llm(self):
        fields = set(get_related_products.tool_call_schema.model_fields)
        assert "runtime" not in fields

    def test_user_params_present(self):
        fields = set(get_related_products.tool_call_schema.model_fields)
        assert fields == {"product_id", "relationship_type", "limit"}


# ── Memory tools (already working — sanity check) ───────────────────────


class TestRememberMessageSchema:
    def test_runtime_hidden_from_llm(self):
        fields = set(remember_message.tool_call_schema.model_fields)
        assert "runtime" not in fields

    def test_user_params_present(self):
        fields = set(remember_message.tool_call_schema.model_fields)
        assert fields == {"content"}


class TestRecallMemorySchema:
    def test_runtime_hidden_from_llm(self):
        fields = set(recall_memory.tool_call_schema.model_fields)
        assert "runtime" not in fields

    def test_no_user_params(self):
        fields = set(recall_memory.tool_call_schema.model_fields)
        assert fields == set()
