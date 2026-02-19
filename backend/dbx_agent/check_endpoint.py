"""Verify the deployed prototype agent endpoint.

Checks the endpoint exists, sends sample queries, and prints responses.

Usage:
    uv run python -m backend.dbx_agent.check_endpoint
"""

import sys

from backend.dbx_agent.config import CONFIG


def check_endpoint() -> int:
    """Run basic checks against the deployed endpoint."""
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    endpoint_name = CONFIG.resolved_endpoint_name

    # Check endpoint exists and is ready
    print(f"Checking endpoint: {endpoint_name}")
    try:
        endpoint = w.serving_endpoints.get(endpoint_name)
        state = endpoint.state.ready if endpoint.state else None
        print(f"  Status: {state}")
    except Exception as e:
        print(f"  Endpoint not found: {e}")
        return 1

    from databricks.sdk.service.serving import EndpointStateReady

    if state != EndpointStateReady.READY:
        print("\n  Endpoint is not ready yet — skipping queries.")
        print("  Re-run this script once the endpoint reaches READY state.")
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
            # response may be a typed object or a raw dict depending on SDK version
            resp = response if isinstance(response, dict) else response.as_dict()
            if "choices" in resp and resp["choices"]:
                text = resp["choices"][0]["message"]["content"]
            elif "messages" in resp and resp["messages"]:
                text = resp["messages"][-1].get("content", str(resp["messages"][-1]))
            else:
                text = str(resp)
            print(f"A: {text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(check_endpoint())
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    check_endpoint()
