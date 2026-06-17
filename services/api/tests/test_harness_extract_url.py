"""Pin the URL selection for web_extract.

The 2026-06-17 source-quality eval surfaced that the harness always called
web_extract on results[0] — when that was an aggregator (stocktitan,
seekingalpha, etc.) we burned an extract call on a rewrite while a real
primary source sat one slot lower. _first_result_url now skips
aggregator-flagged entries.
"""

from __future__ import annotations

from shinkai_api.agent.harness import _first_result_url
from shinkai_api.tools.base import ToolResult


def _result(*entries: dict) -> ToolResult:
    return ToolResult(
        ok=True,
        summary="",
        data={"results": list(entries)},
    )


def test_skips_aggregator_and_returns_first_clean() -> None:
    result = _result(
        {"url": "https://stocktitan.com/x", "is_aggregator": True},
        {"url": "https://semianalysis.com/y", "is_aggregator": False},
        {"url": "https://www.sec.gov/z", "is_aggregator": False},
    )
    assert _first_result_url(result) == "https://semianalysis.com/y"


def test_falls_back_to_first_when_all_are_aggregators() -> None:
    result = _result(
        {"url": "https://stocktitan.com/x", "is_aggregator": True},
        {"url": "https://marketbeat.com/y", "is_aggregator": True},
    )
    assert _first_result_url(result) == "https://stocktitan.com/x"


def test_empty_results_returns_blank() -> None:
    assert _first_result_url(ToolResult(ok=True, data={"results": []})) == ""
    assert _first_result_url(ToolResult(ok=False, data={"results": []})) == ""


def test_missing_aggregator_field_treated_as_clean() -> None:
    # Pre-R1 results don't carry is_aggregator — must still pick results[0].
    result = _result({"url": "https://example.com/x"})
    assert _first_result_url(result) == "https://example.com/x"
