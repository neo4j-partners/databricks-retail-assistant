from __future__ import annotations

import unittest

from agentic_commerce.backend.demo_adapter import (
    adapt_diagnosis_trace,
    adapt_search_trace,
)
from agentic_commerce.backend.router import _safe_error_status
from agentic_commerce.backend.sample_data import diagnosis_sample, search_sample
from agentic_commerce.backend.serving_client import ServingInvocationError


class DemoAdapterTests(unittest.TestCase):
    def test_search_trace_maps_live_product_results(self) -> None:
        adapted = adapt_search_trace(
            {
                "messages": [{"role": "assistant", "content": "Pick this mouse."}],
                "custom_outputs": {
                    "demo_trace": {
                        "trace_source": "live",
                        "product_results": [
                            {
                                "product_id": "p1",
                                "name": "Logitech MX Master 3S",
                                "brand": "Logitech",
                                "price": 99.99,
                                "score": 0.94,
                            }
                        ],
                        "tool_timeline": [{"tool_name": "search_products"}],
                    }
                },
            }
        )

        self.assertEqual(adapted["trace_source"], "live")
        self.assertEqual(adapted["answer"], "Pick this mouse.")
        self.assertEqual(adapted["product_picks"][0].name, "Logitech MX Master 3S")
        self.assertEqual(adapted["tool_timeline"][0].tool_name, "search_products")

    def test_missing_demo_trace_degrades_to_prose(self) -> None:
        adapted = adapt_search_trace(
            {"messages": [{"role": "assistant", "content": "Plain answer."}]}
        )

        self.assertEqual(adapted["trace_source"], "unavailable")
        self.assertEqual(adapted["answer"], "Plain answer.")
        self.assertEqual(adapted["summary"], "Plain answer.")
        self.assertEqual(adapted["warnings"][0].code, "trace_unavailable")

    def test_diagnosis_trace_maps_chunks_to_actions_and_sources(self) -> None:
        adapted = adapt_diagnosis_trace(
            {
                "messages": [{"role": "assistant", "content": "Reset Bluetooth."}],
                "custom_outputs": {
                    "demo_trace": {
                        "knowledge_chunks": [
                            {
                                "chunk_id": "c1",
                                "text": "Calls drop when multipoint switches devices.",
                                "source_type": "SupportTicket",
                                "symptoms": ["disconnects during calls"],
                                "solutions": ["disable multipoint"],
                                "score": 0.9,
                            }
                        ],
                    }
                },
            }
        )

        self.assertEqual(adapted["trace_source"], "live")
        self.assertEqual(adapted["recommended_actions"][0].label, "disable multipoint")
        self.assertEqual(adapted["cited_sources"][0].id, "c1")


class SampleDataTests(unittest.TestCase):
    def test_search_sample_has_session_and_products(self) -> None:
        response = search_sample(
            preset_id="macbook-coding-mouse",
            prompt="mouse",
            request_id="req",
            session_id="session",
        )

        self.assertEqual(response.session_id, "session")
        self.assertEqual(response.source_type, "sample")
        self.assertTrue(response.product_picks)

    def test_diagnosis_sample_has_sources(self) -> None:
        response = diagnosis_sample(
            preset_id="printer-offline",
            prompt="printer offline",
            request_id="req",
            session_id="session",
        )

        self.assertEqual(response.trace_source, "sample")
        self.assertTrue(response.cited_sources)


class ErrorMappingTests(unittest.TestCase):
    def test_safe_error_status_does_not_leak_upstream_404(self) -> None:
        error = ServingInvocationError("missing", status_code=404)

        self.assertEqual(_safe_error_status(error), 502)

    def test_safe_error_status_maps_timeout(self) -> None:
        error = ServingInvocationError("timeout", status_code=504)

        self.assertEqual(_safe_error_status(error), 504)


if __name__ == "__main__":
    unittest.main()
