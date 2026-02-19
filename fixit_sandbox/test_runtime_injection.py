"""Verify that ToolRuntime injection works end-to-end.

Uses a self-contained mock tool (no Neo4j) to prove that:
1. ToolNode with the LangGraph runtime config wires up injection
2. The ToolRuntime object carries the correct .context to async tools
3. The pattern used by the fixed product_search.py actually works at runtime
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, ToolRuntime, tools_condition


# ── Mock context (mirrors RetailContext shape) ───────────────────────────


@dataclass
class MockContext:
    user_id: str = "test-user-42"


# ── Mock tools mirroring the fixed product_search pattern ────────────────


@tool
async def greet_user(
    greeting: str,
    *,
    runtime: ToolRuntime[MockContext],
) -> str:
    """Greet the user by their ID from the injected context."""
    return f"{greeting}, {runtime.context.user_id}!"


@tool
async def get_info(
    runtime: ToolRuntime[MockContext],
) -> str:
    """Return the user ID from context (no user-facing args)."""
    return f"user={runtime.context.user_id}"


# ── Helper: build a minimal graph with ToolNode ──────────────────────────


def _build_graph(tools_list, responses):
    """Build a StateGraph that uses a fake LLM node + ToolNode.

    The fake LLM node pops pre-defined AIMessages from `responses`.
    This avoids needing a real LLM or one that supports bind_tools.
    """
    response_iter = iter(responses)

    def fake_llm(state: MessagesState):
        return {"messages": [next(response_iter)]}

    tool_node = ToolNode(tools_list)

    builder = StateGraph(MessagesState, context_schema=MockContext)
    builder.add_node("llm", fake_llm)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")

    return builder.compile()


# ── Tests ────────────────────────────────────────────────────────────────


class TestToolNodeInjection:
    """Test ToolRuntime injection through a LangGraph StateGraph."""

    def test_schema_hides_runtime(self):
        fields = set(greet_user.tool_call_schema.model_fields)
        assert "runtime" not in fields
        assert fields == {"greeting"}

    @pytest.mark.asyncio
    async def test_injection_with_custom_context(self):
        """Tool receives injected context with custom user_id."""
        graph = _build_graph(
            [greet_user],
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "greet_user", "args": {"greeting": "Hello"}}],
                ),
                AIMessage(content="Done!"),
            ],
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            context=MockContext(user_id="alice"),
        )

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "Hello, alice!"

    @pytest.mark.asyncio
    async def test_injection_with_default_context(self):
        """Tool receives injected context with default user_id."""
        graph = _build_graph(
            [greet_user],
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c2", "name": "greet_user", "args": {"greeting": "Hey"}}],
                ),
                AIMessage(content="Done!"),
            ],
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            context=MockContext(),
        )

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "Hey, test-user-42!"

    @pytest.mark.asyncio
    async def test_injection_no_user_args(self):
        """Tool with only runtime param (no user-facing args) gets injected."""
        graph = _build_graph(
            [get_info],
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c3", "name": "get_info", "args": {}}],
                ),
                AIMessage(content="Done!"),
            ],
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            context=MockContext(user_id="bob"),
        )

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "user=bob"
