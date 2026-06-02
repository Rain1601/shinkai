from __future__ import annotations

import uuid

import pytest

from shinkai_api.core.config import settings


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    state_file = tmp_path / f"state-{uuid.uuid4().hex[:8]}.json"
    monkeypatch.setattr(settings, "state_path", str(state_file))
    monkeypatch.setenv("SHINKAI_STATE_PATH", str(state_file))
    # Strip live API keys from the test session so existing tests don't
    # accidentally start making real Tavily / DeepSeek requests just because
    # the dev .env happens to have them set. Individual tests that need a
    # backed call should monkeypatch the key back on explicitly.
    monkeypatch.setattr(settings, "tavily_api_key", None)

    from shinkai_api.actions.store import default_actions_store
    from shinkai_api.graph.store import default_graph_store
    from shinkai_api.memory.store import default_memory_store
    from shinkai_api.research.store import default_research_store
    from shinkai_api.runs.executor import default_run_executor
    from shinkai_api.runs.store import default_run_store
    from shinkai_api.tools import default_tool_registry
    from shinkai_api.tools.base import Tool, ToolResult
    from shinkai_api.tools.web import WebExtractTool, WebSearchTool

    default_run_store._runs = {}
    default_run_store._loaded = False
    default_graph_store._graphs_by_run = {}
    default_graph_store._loaded = False
    default_research_store._reset_for_tests()
    default_memory_store._reset_for_tests()
    default_actions_store._reset_for_tests()
    default_run_executor._tasks = {}
    default_run_executor._tool_call_counts = {}

    # Register no-op stubs for the live-network tools so harness runs in
    # tests don't accidentally hit yfinance / SEC EDGAR. Individual tests
    # that exercise these tools register a different stub via
    # ``default_tool_registry.register(...)``.
    class _NoopValidator(Tool):
        name = "ticker_validate"
        description = "test stub"

        async def run(self, **_: object) -> ToolResult:
            return ToolResult(ok=False, data={"industry_eligible": True})

    class _NoopSecFilings(Tool):
        name = "sec_filings"
        description = "test stub"

        async def run(self, **_: object) -> ToolResult:
            return ToolResult(ok=False, data={"filings": []})

    default_tool_registry._tools = {}
    default_tool_registry.register(WebSearchTool())
    default_tool_registry.register(WebExtractTool())
    default_tool_registry.register(_NoopValidator())
    default_tool_registry.register(_NoopSecFilings())

    yield
