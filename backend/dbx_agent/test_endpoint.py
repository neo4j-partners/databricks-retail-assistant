"""Test the deployed prototype agent endpoint.

Verifies the endpoint exists, sends sample queries, and checks responses.

Usage:
    uv run python -m backend.dbx_agent.test_endpoint
"""

import sys

from backend.dbx_agent.config import CONFIG


def test_endpoint() -> int:
    """Run basic tests against the deployed endpoint."""
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    endpoint_name = CONFIG.resolved_endpoint_name

    # Check endpoint exists
    print(f"Checking endpoint: {endpoint_name}")
    try:
        endpoint = w.serving_endpoints.get(endpoint_name)
        print(f"  Status: {endpoint.state.ready if endpoint.state else 'unknown'}")
    except Exception as e:
        print(f"  Endpoint not found: {e}")
        return 1

    # Send sample queries
    print()
    print("Running sample queries:")
    print("-" * 40)

    for query in CONFIG.sample_queries:
        print(f"\nQ: {query}")
        try:
            response = w.serving_endpoints.query(
                name=endpoint_name,
                messages=[{"role": "user", "content": query}],
            )
            # Extract response text
            if hasattr(response, "choices") and response.choices:
                text = response.choices[0].message.content
            elif hasattr(response, "messages") and response.messages:
                text = response.messages[-1].get("content", str(response.messages[-1]))
            else:
                text = str(response)
            print(f"A: {text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(test_endpoint())
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    test_endpoint()
