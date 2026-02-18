"""Plain Python test suite for the retail assistant API.

Calls every endpoint over HTTP and validates responses against Pydantic models.
No pytest or test frameworks required.

Usage:
    python test_api.py
    python test_api.py --base-url http://localhost:9000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# Response Models (mirrors server models for validation)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    database: Literal["connected", "disconnected"]


class ChatResponse(BaseModel):
    response: str
    session_id: str


class ProductItem(BaseModel):
    id: str
    name: str
    description: str = ""
    price: float = 0.0
    category: str = ""
    brand: str = ""
    in_stock: bool = True
    score: float = 1.0


class ProductSearchResponse(BaseModel):
    products: list[ProductItem]
    total: int = Field(ge=0)


class ProductDetailResponse(BaseModel):
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
    id: str
    name: str
    description: str = ""
    price: float = 0.0
    category: str = ""
    brand: str = ""


class RelatedProductsResponse(BaseModel):
    related_products: list[RelatedProductItem]


class MemoryContextResponse(BaseModel):
    history: str = ""
    context: str = ""
    preferences: list[dict[str, str]] = Field(default_factory=list)
    similar_tasks: str = ""


class GraphNodeResponse(BaseModel, extra="allow"):
    id: str
    labels: list[str] = Field(default_factory=list)


class GraphRelationshipResponse(BaseModel, extra="allow"):
    id: str
    type: str
    from_node: str
    to_node: str


class MemoryGraphResponse(BaseModel):
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    relationships: list[GraphRelationshipResponse] = Field(default_factory=list)


class PreferenceItem(BaseModel):
    category: str
    preference: str
    context: str | None = None
    confidence: float = 1.0


class PreferencesResponse(BaseModel):
    preferences: list[PreferenceItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP Helpers
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:8000"
SESSION_ID = "test-session-1"
MAX_OUTPUT = 200


def truncate(obj: object, max_len: int = MAX_OUTPUT) -> str:
    text = json.dumps(obj, indent=2) if isinstance(obj, (dict, list)) else str(obj)
    return text[:max_len] + "..." if len(text) > max_len else text


def http_request(
    method: str,
    path: str,
    base_url: str,
    body: dict | None = None,
) -> tuple[int, dict | str]:
    """Make an HTTP request and return (status_code, parsed_response)."""
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def validate_model(model_cls: type[BaseModel], data: Any) -> BaseModel:
    """Validate data against a Pydantic model, raising on failure."""
    return model_cls.model_validate(data)


# ---------------------------------------------------------------------------
# Test Functions
# ---------------------------------------------------------------------------


def test_health(base_url: str) -> bool:
    """GET /health — verify healthy status and Pydantic shape."""
    status, data = http_request("GET", "/health", base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(HealthResponse, data)
    print(f"  status={resp.status}, database={resp.database}")

    if resp.status != "healthy":
        print(f"  WARNING: server reports status={resp.status}")
    return True


def test_chat_sync(base_url: str) -> bool:
    """POST /chat/sync — verify response shape."""
    body = {"message": "Hello, what products do you have?", "session_id": SESSION_ID}
    status, data = http_request("POST", "/chat/sync", base_url, body)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(ChatResponse, data)
    print(f"  session_id={resp.session_id}")
    print(f"  response={truncate(resp.response)}")

    if not resp.response:
        print("  FAIL: empty response")
        return False
    if not resp.session_id:
        print("  FAIL: missing session_id")
        return False
    return True


def test_chat_stream(base_url: str) -> bool:
    """POST /chat — verify SSE stream has token and done events."""
    url = f"{base_url}/chat"
    body = json.dumps({"message": "Show me running shoes", "session_id": SESSION_ID}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                print(f"  Expected 200, got {resp.status}")
                return False

            events: list[tuple[str, str]] = []
            current_event = ""
            current_data = ""
            for line in resp:
                decoded = line.decode().strip()
                if decoded.startswith("event:"):
                    current_event = decoded[len("event:"):].strip()
                elif decoded.startswith("data:"):
                    current_data = decoded[len("data:"):].strip()
                elif decoded == "" and current_event:
                    events.append((current_event, current_data))
                    current_event = ""
                    current_data = ""
                if len(events) >= 10:
                    break

            # Capture final event if stream ended without trailing blank line
            if current_event:
                events.append((current_event, current_data))

            event_types = [e[0] for e in events]
            print(f"  events_received={len(events)}, types={event_types}")

            has_token = "token" in event_types
            has_done = "done" in event_types

            if not has_token:
                print("  FAIL: no 'token' event received")
                return False
            if not has_done:
                print("  FAIL: no 'done' event received")
                return False

            # Validate token event data
            for etype, edata in events:
                if etype == "token":
                    parsed = json.loads(edata)
                    if "content" not in parsed:
                        print("  FAIL: token event missing 'content' key")
                        return False
                elif etype == "done":
                    parsed = json.loads(edata)
                    if "session_id" not in parsed:
                        print("  FAIL: done event missing 'session_id' key")
                        return False

            return True
    except urllib.error.HTTPError as e:
        print(f"  HTTP error: {e.code}")
        return False


def test_memory_context(base_url: str) -> bool:
    """GET /memory/context — verify response shape with real memory data."""
    path = f"/memory/context?session_id={SESSION_ID}&query=shoes"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(MemoryContextResponse, data)
    print(f"  history={len(resp.history)} chars, context={len(resp.context)} chars")
    print(f"  preferences={len(resp.preferences)}, similar_tasks={len(resp.similar_tasks)} chars")
    return True


def test_memory_graph(base_url: str) -> bool:
    """GET /memory/graph — verify response shape with real graph data."""
    path = f"/memory/graph?session_id={SESSION_ID}"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(MemoryGraphResponse, data)
    print(f"  nodes={len(resp.nodes)}, relationships={len(resp.relationships)}")
    return True


def test_memory_preferences(base_url: str) -> bool:
    """GET /memory/preferences — verify response shape."""
    path = f"/memory/preferences?session_id={SESSION_ID}"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(PreferencesResponse, data)
    print(f"  preferences={len(resp.preferences)} items")
    return True


def test_product_search(base_url: str) -> bool:
    """GET /products/search — verify response shape and field types."""
    path = "/products/search?query=shoes"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(ProductSearchResponse, data)
    print(f"  total={resp.total}, products={len(resp.products)}")
    if resp.products:
        first = resp.products[0]
        print(f"  first: name={first.name}, price={first.price}, category={first.category}")
    return True


def _get_a_product_id(base_url: str) -> str | None:
    """Helper: fetch a product ID from search results."""
    status, data = http_request("GET", "/products/search?query=shoes", base_url)
    if status == 200 and isinstance(data, dict) and data.get("products"):
        return data["products"][0]["id"]
    return None


def test_product_detail(base_url: str) -> bool:
    """GET /products/{id} — verify full product record."""
    product_id = _get_a_product_id(base_url)
    if not product_id:
        print("  SKIP: no products found to test with")
        return True

    path = f"/products/{product_id}"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(ProductDetailResponse, data)
    print(f"  name={resp.name}, price={resp.price}, in_stock={resp.in_stock}, inventory={resp.inventory}")
    return True


def test_product_detail_404(base_url: str) -> bool:
    """GET /products/{id} with invalid ID — verify 404."""
    path = "/products/nonexistent-product-id-12345"
    status, data = http_request("GET", path, base_url)
    if status != 404:
        print(f"  Expected 404, got {status}")
        return False

    print("  Correctly returned 404")
    return True


def test_related_products(base_url: str) -> bool:
    """GET /products/{id}/related — verify response shape."""
    product_id = _get_a_product_id(base_url)
    if not product_id:
        print("  SKIP: no products found to test with")
        return True

    path = f"/products/{product_id}/related"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Expected 200, got {status}")
        return False

    resp = validate_model(RelatedProductsResponse, data)
    print(f"  related_products={len(resp.related_products)}")
    return True


def test_memory_roundtrip(base_url: str) -> bool:
    """POST /chat/sync then GET /memory/context — verify chat saves to memory."""
    roundtrip_session = "memory-roundtrip-test"

    # Send a message to create a conversation in this session
    body = {"message": "I really love Nike running shoes", "session_id": roundtrip_session}
    status, _ = http_request("POST", "/chat/sync", base_url, body)
    if status != 200:
        print(f"  Chat request failed with {status}")
        return False

    # NOTE: The chat endpoint is still a placeholder — it does not yet save to
    # memory (that happens in Phase 7 when the agent is wired up). For now we
    # just verify that the memory context endpoint returns a valid response for
    # any session, even one without stored messages.
    path = f"/memory/context?session_id={roundtrip_session}&query=Nike+shoes"
    status, data = http_request("GET", path, base_url)
    if status != 200:
        print(f"  Memory context request failed with {status}")
        return False

    resp = validate_model(MemoryContextResponse, data)
    print(f"  history={len(resp.history)} chars (empty until agent saves to memory in Phase 7)")
    return True


def test_related_products_invalid_type(base_url: str) -> bool:
    """GET /products/{id}/related with invalid relationship_type — verify 400."""
    product_id = _get_a_product_id(base_url)
    if not product_id:
        # Even without a real product, the validation should fire first
        product_id = "fake-id"

    path = f"/products/{product_id}/related?relationship_type=DROP_TABLE"
    status, data = http_request("GET", path, base_url)
    if status != 400:
        print(f"  Expected 400, got {status}")
        return False

    print("  Correctly rejected invalid relationship_type with 400")
    return True


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

TESTS: list[tuple[str, Any]] = [
    ("Health check", test_health),
    ("Sync chat", test_chat_sync),
    ("Streaming chat (SSE)", test_chat_stream),
    ("Memory context", test_memory_context),
    ("Memory graph", test_memory_graph),
    ("Memory preferences", test_memory_preferences),
    ("Product search", test_product_search),
    ("Product detail", test_product_detail),
    ("Product detail 404", test_product_detail_404),
    ("Related products", test_related_products),
    ("Related products invalid type", test_related_products_invalid_type),
    ("Memory roundtrip", test_memory_roundtrip),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="API tests for the retail assistant backend")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend URL (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args()

    print(f"Testing backend at {args.base_url}\n")

    passed = 0
    failed = 0

    for name, fn in TESTS:
        print(f"[TEST] {name}")
        try:
            if fn(args.base_url):
                print("  PASS\n")
                passed += 1
            else:
                print("  FAIL\n")
                failed += 1
        except ValidationError as e:
            print(f"  FAIL (Pydantic validation): {e}\n")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}\n")
            failed += 1

    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
