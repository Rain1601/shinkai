from __future__ import annotations

import asyncio
from typing import Any

import pytest

from shinkai_api.tools.ticker_validator import (
    INELIGIBLE_INDUSTRIES,
    INELIGIBLE_SECTORS,
    TickerValidatorTool,
    _resolve_via_sec,
)


@pytest.fixture(autouse=True)
def _reset_sec_cache():
    from shinkai_api.tools.ticker_validator import _reset_ticker_index_cache_for_tests

    _reset_ticker_index_cache_for_tests()
    yield
    _reset_ticker_index_cache_for_tests()


class _StubTicker:
    def __init__(self, info: dict[str, Any]):
        self.info = info


def _patch_yfinance(monkeypatch: pytest.MonkeyPatch, info: dict[str, Any]) -> None:
    import sys
    import types

    stub = types.ModuleType("yfinance")
    stub.Ticker = lambda symbol: _StubTicker(info)  # type: ignore[assignment]
    monkeypatch.setitem(sys.modules, "yfinance", stub)


def test_validator_rejects_healthcare_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_yfinance(
        monkeypatch,
        {
            "longName": "aTyr Pharma Inc.",
            "sector": "Healthcare",
            "industry": "Biotechnology",
            "longBusinessSummary": "biotech company developing therapies",
            "exchange": "NMS",
            "marketCap": 100_000_000,
        },
    )
    tool = TickerValidatorTool()
    result = asyncio.run(tool.run(ticker="ATYR"))
    assert result.ok is True  # ticker was found
    assert result.data["industry_eligible"] is False
    assert "Healthcare" in result.data["reject_reason"]


def test_validator_rejects_casino_industry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_yfinance(
        monkeypatch,
        {
            "longName": "Boyd Gaming Corporation",
            "sector": "Consumer Cyclical",
            "industry": "Resorts & Casinos",
            "exchange": "NYQ",
            "marketCap": 5_000_000_000,
        },
    )
    tool = TickerValidatorTool()
    result = asyncio.run(tool.run(ticker="BYD"))
    assert result.data["industry_eligible"] is False
    assert "Resorts" in result.data["reject_reason"]


def test_validator_passes_technology_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_yfinance(
        monkeypatch,
        {
            "longName": "NVIDIA Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
            "exchange": "NMS",
            "marketCap": 3_000_000_000_000,
        },
    )
    tool = TickerValidatorTool()
    result = asyncio.run(tool.run(ticker="NVDA"))
    assert result.ok is True
    assert result.data["industry_eligible"] is True
    assert result.data["reject_reason"] == ""
    assert result.data["sector"] == "Technology"
    assert result.data["found_via"] == "yfinance"


def test_validator_returns_not_found_when_yfinance_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_yfinance(monkeypatch, {})  # empty info — yfinance signals "not found"
    monkeypatch.setattr(
        "shinkai_api.tools.ticker_validator._resolve_via_sec", lambda ticker: None
    )
    tool = TickerValidatorTool()
    result = asyncio.run(tool.run(ticker="ZZZZZ"))
    assert result.ok is False
    assert result.data["found"] is False


def test_ineligible_sets_have_expected_anchors() -> None:
    # Sanity: catch typos in the canonical lists.
    assert "Healthcare" in INELIGIBLE_SECTORS
    assert "Real Estate" in INELIGIBLE_SECTORS
    assert "Resorts & Casinos" in INELIGIBLE_INDUSTRIES


def test_resolve_via_sec_uses_cached_index(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-populate the cache directly to avoid real HTTP calls.
    from shinkai_api.tools import ticker_validator as tv

    tv._TICKER_INDEX_CACHE = {
        "NVDA": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    payload = _resolve_via_sec("NVDA")
    assert payload is not None
    assert payload["name"] == "NVIDIA CORP"
    assert payload["cik"] == "1045810"
