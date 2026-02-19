"""Verify the deployed agent endpoint on Databricks.

Checks the endpoint exists, sends sample queries from CONFIG, and prints responses.
Uses raw REST calls (like aircraft_analyst) instead of the SDK's query() method,
which can have issues deserializing ChatAgent responses.

Usage:
    uv run python -m dbx_agent.check_endpoint
"""

import os
import sys

import requests

from dbx_agent.config import CONFIG


def _get_workspace_url_and_token() -> tuple[str, str]:
    """Get Databricks workspace URL and auth token.

    Tries dbutils (notebook), then WorkspaceClient (CLI/jobs),
    then environment variables.
    """
    # Method 1: dbutils notebook context
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        dbutils = DBUtils(spark)
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        url = ctx.apiUrl().get().rstrip("/")
        token = ctx.apiToken().get()
        if url and token:
            return url, token
    except Exception:
        pass

    # Method 2: WorkspaceClient config
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        url = (w.config.host or "").rstrip("/")
        token = w.config.token or ""
        if url and token:
            return url, token
    except Exception:
        pass

    # Method 3: Environment variables
    url = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if url and token:
        return url, token

    raise ValueError("Could not determine Databricks workspace URL and token")


def _extract_content(result: dict) -> str | None:
    """Extract text content from a ChatAgent or standard response.

    ChatAgent format:  {"messages": [{"role": "assistant", "content": "..."}]}
    Standard format:   {"choices": [{"message": {"content": "..."}}]}
    ResponsesAgent:    {"output": [{"type": "message", "content": [{"type": "output_text", "text": "..."}]}]}
    """
    # ChatAgent format
    if "messages" in result and result["messages"]:
        last = result["messages"][-1]
        return last.get("content", str(last))

    # Standard completion format
    if "choices" in result and result["choices"]:
        return result["choices"][0]["message"]["content"]

    # ResponsesAgent format
    if "output" in result:
        for item in result.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        return part.get("text")

    return None


def check_endpoint() -> int:
    """Run basic checks against the deployed endpoint."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import EndpointStateReady

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

    if state != EndpointStateReady.READY:
        print("\n  Endpoint is not ready yet — skipping queries.")
        print("  Re-run this script once the endpoint reaches READY state.")
        return 1

    # Get auth for raw REST calls
    try:
        workspace_url, token = _get_workspace_url_and_token()
    except ValueError as e:
        print(f"  Auth error: {e}")
        return 1

    endpoint_url = f"{workspace_url}/serving-endpoints/{endpoint_name}/invocations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Run diagnostics check
    print()
    print("Running diagnostics:")
    print("-" * 40)
    try:
        diag_payload = {"messages": [{"role": "user", "content": "Run agent_diagnostics and return the raw JSON output only, no commentary."}]}
        resp = requests.post(endpoint_url, headers=headers, json=diag_payload, timeout=120)
        resp.raise_for_status()
        result = resp.json()
        text = _extract_content(result)
        if text:
            print(text)
        else:
            print(f"(raw): {result}")
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

    # Send sample queries
    print()
    print("Running sample queries:")
    print("-" * 40)

    for query in CONFIG.sample_queries:
        print(f"\nQ: {query}")
        try:
            payload = {"messages": [{"role": "user", "content": query}]}
            resp = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            result = resp.json()
            text = _extract_content(result)
            if text:
                print(f"A: {text[:500]}")
            else:
                print(f"A (raw): {result}")
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(check_endpoint())
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    check_endpoint()
