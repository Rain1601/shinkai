"""Verify WebSearchTool's QuotaExceeded retry + strategy fallback chain.

The 2026-06-17 source-quality eval hit a Vertex 429 on the 6th query and
the old harness path crashed out with a bare ToolResult(ok=False) instead
of trying the next configured strategy. These tests pin the new behaviour:
one short retry on the primary, then walk the fallback chain.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from market_utils.core.errors import NotConfigured, QuotaExceeded
from market_utils.core.schemas import SearchResult

from shinkai_api.tools.web import WebSearchTool, _build_attempt_order


def _ok_result(url: str = "https://example.com/x") -> SearchResult:
    return SearchResult(
        title="ok", url=url, snippet="s", source="example.com",
        published_at=None, score=None,
    )


def test_build_attempt_order_auto_uses_full_chain() -> None:
    assert _build_attempt_order("auto") == [
        "vertex_grounding", "tavily", "google", "duckduckgo",
    ]


def test_build_attempt_order_explicit_strategy_first_then_chain() -> None:
    assert _build_attempt_order("tavily") == [
        "tavily", "vertex_grounding", "google", "duckduckgo",
    ]


def test_quota_on_primary_retries_once_then_falls_back() -> None:
    calls: list[str] = []

    async def fake_run_strategy(
        strategy: str, query: str, max_results: int, date_restrict: Any, topic: Any
    ) -> tuple[str, list[SearchResult]]:
        calls.append(strategy)
        if strategy == "vertex_grounding":
            raise QuotaExceeded("burst 429")
        return strategy, [_ok_result()]

    async def scenario() -> None:
        with patch("shinkai_api.tools.web._run_strategy", side_effect=fake_run_strategy):
            result = await WebSearchTool().run(query="HBM supplier", strategy="auto")

        # Vertex tried twice (primary + 1 backoff retry), then tavily wins.
        assert calls == ["vertex_grounding", "vertex_grounding", "tavily"]
        assert result.ok is True
        assert result.data["backend"] == "tavily"
        assert len(result.data["results"]) == 1
        assert any("retry_failed" in a["error"] for a in result.data["attempts"])

    asyncio.run(scenario())


def test_not_configured_silently_skips_to_next() -> None:
    async def fake_run_strategy(
        strategy: str, query: str, max_results: int, date_restrict: Any, topic: Any
    ) -> tuple[str, list[SearchResult]]:
        if strategy in {"vertex_grounding", "tavily", "google"}:
            raise NotConfigured(f"{strategy} not configured")
        return strategy, [_ok_result()]

    async def scenario() -> None:
        with patch("shinkai_api.tools.web._run_strategy", side_effect=fake_run_strategy):
            result = await WebSearchTool().run(query="x", strategy="auto")

        assert result.ok is True
        assert result.data["backend"] == "duckduckgo"
        skipped = {a["strategy"] for a in result.data["attempts"]}
        assert skipped == {"vertex_grounding", "tavily", "google"}

    asyncio.run(scenario())


def test_all_backends_failed_returns_diagnostic_result() -> None:
    async def fake_run_strategy(
        strategy: str, query: str, max_results: int, date_restrict: Any, topic: Any
    ) -> tuple[str, list[SearchResult]]:
        raise NotConfigured(f"{strategy} not configured")

    async def scenario() -> None:
        with patch("shinkai_api.tools.web._run_strategy", side_effect=fake_run_strategy):
            result = await WebSearchTool().run(query="x", strategy="auto")

        assert result.ok is False
        assert "all configured search backends failed" in (result.error or "")
        # Every chain member attempted exactly once — only the primary
        # retries, and only on QuotaExceeded specifically.
        assert {a["strategy"] for a in result.data["attempts"]} == {
            "vertex_grounding", "tavily", "google", "duckduckgo",
        }

    asyncio.run(scenario())


def test_noise_sources_dropped_after_successful_strategy() -> None:
    noise_url = "https://holdingschannel.com/risk-factors/nvda-risk-factors/"

    async def fake_run_strategy(
        strategy: str, query: str, max_results: int, date_restrict: Any, topic: Any
    ) -> tuple[str, list[SearchResult]]:
        return strategy, [
            _ok_result(noise_url),
            _ok_result("https://www.sec.gov/Archives/edgar/data/x"),
            # Duplicate URL — should be deduped.
            _ok_result("https://www.sec.gov/Archives/edgar/data/x"),
        ]

    async def scenario() -> None:
        with patch("shinkai_api.tools.web._run_strategy", side_effect=fake_run_strategy):
            result = await WebSearchTool().run(query="x", strategy="auto")

        assert result.ok is True
        urls = [r["url"] for r in result.data["results"]]
        assert urls == ["https://www.sec.gov/Archives/edgar/data/x"]
        assert result.data["noise_dropped"] == 1

    asyncio.run(scenario())
