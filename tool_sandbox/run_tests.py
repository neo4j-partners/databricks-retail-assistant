"""Local reproduction tests for ToolRuntime injection failures.

Simulates the Databricks Model Serving environment locally to isolate
why product search tools receive runtime=None while memory tools work.

Uses a FakeToolCallingLLM that deterministically calls specific tools,
so no Databricks credentials or real LLM needed.

Usage:
    uv run python tool_sandbox/run_tests.py
"""

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared context (mirrors dbx_agent/context.py)
# ---------------------------------------------------------------------------

@dataclass
class FakeContext:
    """Stands in for RetailContext — no Neo4j needed."""
    value: str = "fake-client"
    session_id: str = "test-session"


# ---------------------------------------------------------------------------
# Tool definitions — mirrors the two patterns in dbx_agent/
# ---------------------------------------------------------------------------

# Pattern A: memory-style (no args_schema, no default on runtime)
@tool
async def memory_style_tool(
    content: str,
    runtime: ToolRuntime[FakeContext],
) -> str:
    """Memory-style tool — no args_schema."""
    ctx = runtime.context
    return json.dumps({"pattern": "memory_style", "runtime_ok": True, "value": ctx.value})


# Pattern B: product-search-style (explicit args_schema, runtime default=None)
class SearchInput(BaseModel):
    query: str = Field(description="Search query")
    category: str | None = Field(default=None, description="Category filter")
    max_price: float | None = Field(default=None, ge=0, description="Max price")
    limit: int = Field(default=10, ge=1, le=50, description="Max results")


@tool(args_schema=SearchInput)
async def product_style_tool(
    query: str,
    category: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
    runtime: ToolRuntime[FakeContext] = None,
) -> str:
    """Product-search-style tool — with args_schema."""
    if runtime is None:
        return json.dumps({"pattern": "product_style", "runtime_ok": False, "error": "runtime is None"})
    ctx = runtime.context
    return json.dumps({"pattern": "product_style", "runtime_ok": True, "value": ctx.value})


# Pattern C: product-search-style but WITHOUT args_schema (proposed fix)
@tool
async def product_style_no_schema(
    query: str,
    category: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
    runtime: ToolRuntime[FakeContext] = None,
) -> str:
    """Product-search-style tool — without args_schema (proposed fix)."""
    if runtime is None:
        return json.dumps({"pattern": "product_no_schema", "runtime_ok": False, "error": "runtime is None"})
    ctx = runtime.context
    return json.dumps({"pattern": "product_no_schema", "runtime_ok": True, "value": ctx.value})


# Sync diagnostics tool (should always work)
@tool
def diagnostics_tool(
    runtime: ToolRuntime[FakeContext],
) -> str:
    """Sync diagnostics tool."""
    ctx = runtime.context
    return json.dumps({"pattern": "diagnostics", "runtime_ok": True, "value": ctx.value})


ALL_TOOLS = [memory_style_tool, product_style_tool, product_style_no_schema, diagnostics_tool]

SYSTEM_PROMPT = "You are a test agent. Use your tools when asked."


# ---------------------------------------------------------------------------
# Fake LLM that deterministically calls tools
# ---------------------------------------------------------------------------

class FakeToolCallingLLM(BaseChatModel):
    """LLM that calls a specific tool on first turn, returns summary on second."""

    tool_name: str = ""
    tool_args: dict = {}

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Check if we already have a tool result
        has_tool_result = any(
            hasattr(m, "type") and m.type == "tool" for m in messages
        )
        if has_tool_result:
            # Second turn: return final answer
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Done."))]
            )
        # First turn: call the tool
        msg = AIMessage(
            content="",
            tool_calls=[{
                "name": self.tool_name,
                "args": self.tool_args,
                "id": f"call_{self.tool_name}",
            }],
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools: list, **kwargs: Any) -> "FakeToolCallingLLM":
        """Required by create_react_agent — return self since tools are hardcoded."""
        return self


# ---------------------------------------------------------------------------
# Agent factory (mirrors dbx_agent/agent.py)
# ---------------------------------------------------------------------------

def create_agent(tool_name: str, tool_args: dict):
    """Create a LangGraph agent that will call a specific tool."""
    from langgraph.prebuilt import create_react_agent

    llm = FakeToolCallingLLM(tool_name=tool_name, tool_args=tool_args)
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
        context_schema=FakeContext,
    )


# ---------------------------------------------------------------------------
# Persistent background loop (mirrors dbx_agent/serving.py)
# ---------------------------------------------------------------------------

def _create_background_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()),
        daemon=True,
    )
    thread.start()
    return loop


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

TOOL_TESTS = [
    ("memory_style_tool", {"content": "my favorite color is blue"}),
    ("product_style_tool", {"query": "running shoes", "max_price": 100.0}),
    ("product_style_no_schema", {"query": "hiking boots"}),
    ("diagnostics_tool", {}),
]


def _header(msg: str) -> None:
    print()
    print("=" * 60)
    print(msg)
    print("=" * 60)


def _check_result(result: dict, tool_name: str) -> None:
    """Extract and print tool results from agent output."""
    tool_msgs = [m for m in result["messages"]
                 if hasattr(m, "type") and m.type == "tool"]
    for tm in tool_msgs:
        try:
            data = json.loads(tm.content)
            status = "PASS" if data.get("runtime_ok") else "FAIL"
            print(f"  {tm.name}: {status} — {data}")
        except json.JSONDecodeError:
            print(f"  {tm.name}: raw — {tm.content[:200]}")
    if not tool_msgs:
        ai_msgs = [m for m in result["messages"]
                   if hasattr(m, "type") and m.type == "ai" and m.content]
        if ai_msgs:
            print(f"  (no tool called) AI: {ai_msgs[-1].content[:200]}")


# ---------------------------------------------------------------------------
# Test 1: Direct ainvoke (baseline, no agent)
# ---------------------------------------------------------------------------

def test_1_direct_ainvoke():
    """Direct tool.ainvoke — baseline."""
    _header("Test 1: Direct ainvoke (baseline)")

    async def _run():
        tr = ToolRuntime(
            state={"messages": []},
            tool_call_id="t1",
            config={},
            context=FakeContext(value="direct-inject"),
            store=None,
            stream_writer=None,
        )

        for tool_name, tool_args in TOOL_TESTS:
            t = {t.name: t for t in ALL_TOOLS}[tool_name]
            call = {"name": t.name, "args": {**tool_args, "runtime": tr},
                    "id": "t1", "type": "tool_call"}
            result = await t.ainvoke(call)
            data = json.loads(result.content)
            status = "PASS" if data.get("runtime_ok") else "FAIL"
            print(f"  {tool_name}: {status} — {data}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 2: Full agent via asyncio.run (like a normal async call)
# ---------------------------------------------------------------------------

def test_2_full_agent():
    """Full agent with create_react_agent + context_schema via asyncio.run."""
    _header("Test 2: Full agent (asyncio.run)")

    async def _run():
        context = FakeContext(value="agent-context")
        for tool_name, tool_args in TOOL_TESTS:
            agent = create_agent(tool_name, tool_args)
            request = {"messages": [{"role": "user", "content": f"call {tool_name}"}]}
            try:
                result = await agent.ainvoke(request, context=context)
                _check_result(result, tool_name)
            except Exception as e:
                print(f"  {tool_name}: ERROR — {type(e).__name__}: {e}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 3: Agent via run_coroutine_threadsafe (simulate serving.py)
# ---------------------------------------------------------------------------

def test_3_background_loop():
    """Agent invoked via run_coroutine_threadsafe — simulate serving.py."""
    _header("Test 3: run_coroutine_threadsafe (simulate serving.py)")

    loop = _create_background_loop()

    for tool_name, tool_args in TOOL_TESTS:
        agent = create_agent(tool_name, tool_args)

        async def _async_predict(agent=agent):
            context = FakeContext(value="bg-loop-context")
            request = {"messages": [{"role": "user", "content": f"call {tool_name}"}]}
            return await agent.ainvoke(request, context=context)

        try:
            future = asyncio.run_coroutine_threadsafe(_async_predict(), loop)
            result = future.result(timeout=30)
            _check_result(result, tool_name)
        except Exception as e:
            print(f"  {tool_name}: ERROR — {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Tool Sandbox — ToolRuntime Injection Tests")
    print(f"langchain-core: {__import__('langchain_core').__version__}")
    try:
        from importlib.metadata import version as pkg_version
        print(f"langgraph: {pkg_version('langgraph')}")
    except Exception:
        print("langgraph: (version unknown)")

    test_1_direct_ainvoke()
    test_2_full_agent()
    test_3_background_loop()

    _header("Done")
