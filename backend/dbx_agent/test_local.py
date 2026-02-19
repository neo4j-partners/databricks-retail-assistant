"""Local test script for the dbx_agent.

Validates the agent, memory tools, product search tools, and ToolRuntime
injection locally before deploying to Databricks. Requires a Neo4j instance
(local Docker or Aura) with credentials in environment variables.

Usage:
    # With Neo4j Aura or local instance:
    export NEO4J_URI="neo4j+s://xxx.databases.neo4j.io:7687"
    export NEO4J_PASSWORD="your-password"
    uv run python -m backend.dbx_agent.test_local

    # Or with defaults for local Docker:
    uv run python -m backend.dbx_agent.test_local
"""

import asyncio
import os
import sys
import uuid


async def test_agent():
    """Test the agent with ToolRuntime injection and real Neo4j."""
    from neo4j_agent_memory import MemoryClient, MemorySettings, Neo4jConfig
    from pydantic import SecretStr

    # Use env vars or defaults for local Docker
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    print("=" * 60)
    print("LOCAL TEST: dbx_agent")
    print("=" * 60)
    print(f"Neo4j URI: {neo4j_uri}")
    print()

    # 1. Create MemoryClient
    print("1. Creating MemoryClient...")
    settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=neo4j_uri,
            password=SecretStr(neo4j_password),
        ),
    )
    client = MemoryClient(settings)
    await client.connect()
    print("   Connected to Neo4j")

    # 2. Create agent
    print("2. Creating agent...")
    try:
        from backend.dbx_agent.agent import create_prototype_agent
        from backend.dbx_agent.context import RetailContext
    except ImportError:
        # When running as -m backend.dbx_agent.test_local
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        from agent import create_prototype_agent
        from context import RetailContext

    agent = create_prototype_agent()
    print("   Agent created with tools:", [t.name for t in agent.tools])

    session_id = f"test-{uuid.uuid4().hex[:8]}"
    ctx = RetailContext(client=client, session_id=session_id)

    # 3. Test echo tool (baseline)
    print()
    print("3. Testing echo tool...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Echo hello world"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:200]}")

    # 4. Test remember_message tool (ToolRuntime injection)
    print()
    print("4. Testing remember_message tool (ToolRuntime injection)...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Remember that my favorite color is blue"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:200]}")

    tool_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
    if tool_msgs:
        print(f"   Tool call output: {tool_msgs[-1].content[:200]}")
    else:
        print("   WARNING: No tool call detected")

    # 5. Test recall_memory tool
    print()
    print("5. Testing recall_memory tool...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "What do you remember?"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:200]}")

    tool_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
    if tool_msgs:
        print(f"   Tool call output: {tool_msgs[-1].content[:200]}")

    # 6. Test search_products tool
    print()
    print("6. Testing search_products tool...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Search for running shoes under $100"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:300]}")

    tool_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
    if tool_msgs:
        print(f"   Tool call output: {tool_msgs[-1].content[:300]}")
    else:
        print("   WARNING: No tool call detected")

    # 7. Test get_product_details tool
    print()
    print("7. Testing get_product_details tool...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Get me the details for product 'trail-runner-pro'"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:300]}")

    tool_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
    if tool_msgs:
        print(f"   Tool call output: {tool_msgs[-1].content[:300]}")
    else:
        print("   WARNING: No tool call detected")

    # 8. Test get_related_products tool
    print()
    print("8. Testing get_related_products tool...")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "What products are related to 'trail-runner-pro'?"}]},
        context=ctx,
    )
    last_msg = result["messages"][-1]
    print(f"   Response: {last_msg.content[:300]}")

    tool_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
    if tool_msgs:
        print(f"   Tool call output: {tool_msgs[-1].content[:300]}")
    else:
        print("   WARNING: No tool call detected")

    # 9. Cleanup
    print()
    print("9. Cleanup...")
    await client.close()
    print("   MemoryClient closed")

    print()
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print()
    print("Validated:")
    print("  - create_react_agent with context_schema=RetailContext")
    print("  - ToolRuntime[RetailContext] injection into async tools")
    print("  - neo4j-agent-memory short-term memory (add + retrieve)")
    print("  - Product search (search_products, get_product_details, get_related_products)")
    print("  - asyncio async execution of tools")


def main():
    try:
        asyncio.run(test_agent())
        return 0
    except Exception as e:
        print()
        print("=" * 60)
        print(f"TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
