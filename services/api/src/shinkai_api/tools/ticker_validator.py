"""Ticker validator — resolve a ticker symbol to its real-world identity.

Sits between the LLM's "this looks like a supply-chain candidate" and the
harness's "build a dossier for it". The LLM is happy to propose tickers that
*sound right* (ATYR for HBM substrates, BOYD for liquid cooling) without
checking that the ticker is the right company in the right industry. This
tool catches those before they pollute the dossier.

Resolution chain:
  1. yfinance ``Ticker(ticker).info`` — covers ~99% of US-listed names.
  2. SEC EDGAR ``company_tickers.json`` — fallback when yfinance has nothing.

Returns a structured payload + an ``industry_eligible`` boolean that the
harness uses as a hard filter. A handful of sectors are wrong-by-default for
the AI supply-chain thesis (Healthcare, Real Estate, Financial Services,
Utilities, Lodging/Casino, Consumer Defensive) and are rejected outright.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any

from shinkai_api.tools.base import Tool, ToolResult

# SEC requires a UA in this approximate format. Keep it stable so we don't
# trip their rate limiter on the way in.
SEC_USER_AGENT = "shinkai-research-agent rain@shinkai.local"
SEC_TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers.json"

# Hard filter: if yfinance reports the ticker's sector falls in this set,
# the candidate is wrong-industry-by-default for an AI supply-chain layer.
INELIGIBLE_SECTORS: set[str] = {
    "Healthcare",
    "Real Estate",
    "Financial Services",
    "Financial",
    "Utilities",
    "Consumer Defensive",
    "Communication Services",
}

# Within Consumer Cyclical the casino / lodging / restaurant industries are
# also wrong-by-default; we filter them at the industry level.
INELIGIBLE_INDUSTRIES: set[str] = {
    "Resorts & Casinos",
    "Lodging",
    "Restaurants",
    "Gambling",
    "Apparel Retail",
    "Auto & Truck Dealerships",
}


def _normalise(value: Any) -> str:
    return str(value or "").strip()


def _eligible(sector: str, industry: str) -> tuple[bool, str]:
    sector_n = _normalise(sector)
    industry_n = _normalise(industry)
    if sector_n in INELIGIBLE_SECTORS:
        return False, f"sector_blacklisted: {sector_n}"
    if industry_n in INELIGIBLE_INDUSTRIES:
        return False, f"industry_blacklisted: {industry_n}"
    return True, ""


class TickerValidatorTool(Tool):
    name = "ticker_validate"
    description = (
        "Resolve a ticker to its real-world identity (sector, industry, "
        "business summary) and reject candidates that fall in industries "
        "wrong-by-default for the AI supply-chain thesis."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
        },
        "required": ["ticker"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        raw_ticker = _normalise(kwargs.get("ticker")).upper()
        if not raw_ticker:
            return ToolResult(ok=False, error="ticker is required")
        try:
            payload = await asyncio.to_thread(_resolve, raw_ticker)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"validator failed for {raw_ticker}",
                data={"ticker": raw_ticker},
            )

        sector = payload.get("sector", "")
        industry = payload.get("industry", "")
        eligible, reason = _eligible(sector, industry)
        payload["industry_eligible"] = eligible
        payload["reject_reason"] = reason

        return ToolResult(
            ok=bool(payload.get("found")),
            summary=(
                f"{raw_ticker}: {payload.get('name','?')} · "
                f"{sector or 'unknown sector'} · "
                f"eligible={eligible}"
            ),
            data=payload,
            error=None if payload.get("found") else "ticker not found",
        )


def _resolve(ticker: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ticker": ticker,
        "found": False,
        "found_via": None,
        "name": "",
        "sector": "",
        "industry": "",
        "business_summary": "",
        "market_cap": None,
        "exchange": "",
        "cik": None,
    }
    yf_payload = _resolve_via_yfinance(ticker)
    if yf_payload:
        payload.update(yf_payload)
        payload["found"] = True
        payload["found_via"] = "yfinance"
        return payload
    sec_payload = _resolve_via_sec(ticker)
    if sec_payload:
        payload.update(sec_payload)
        payload["found"] = True
        payload["found_via"] = "sec_edgar"
    return payload


def _resolve_via_yfinance(ticker: str) -> dict[str, Any] | None:
    try:
        import yfinance as yf  # local import — keep cold-start cheap

        info = yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001
        return None
    if not info:
        return None
    # yfinance returns a sparse dict when ticker doesn't exist. Use a real
    # field as the existence check.
    name = info.get("longName") or info.get("shortName") or ""
    if not name:
        return None
    return {
        "name": name,
        "sector": info.get("sector") or "",
        "industry": info.get("industryDisp") or info.get("industry") or "",
        "business_summary": (info.get("longBusinessSummary") or "")[:600],
        "market_cap": info.get("marketCap"),
        "exchange": info.get("exchange") or info.get("fullExchangeName") or "",
    }


_TICKER_INDEX_CACHE: dict[str, dict[str, Any]] | None = None


def _load_sec_ticker_index() -> dict[str, dict[str, Any]]:
    global _TICKER_INDEX_CACHE
    if _TICKER_INDEX_CACHE is not None:
        return _TICKER_INDEX_CACHE
    request = urllib.request.Request(
        SEC_TICKER_INDEX_URL,
        headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        _TICKER_INDEX_CACHE = {}
        return _TICKER_INDEX_CACHE
    data = json.loads(raw)
    index: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        # The SEC publishes either {"0": {...}, "1": {...}} OR the new
        # company_tickers.json shape. Cover both.
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            ticker = _normalise(entry.get("ticker")).upper()
            if not ticker:
                continue
            index[ticker] = entry
    _TICKER_INDEX_CACHE = index
    return _TICKER_INDEX_CACHE


def _resolve_via_sec(ticker: str) -> dict[str, Any] | None:
    index = _load_sec_ticker_index()
    entry = index.get(ticker)
    if not entry:
        return None
    cik_raw = entry.get("cik_str") or entry.get("cik")
    cik = re.sub(r"\D", "", str(cik_raw)) if cik_raw is not None else ""
    return {
        "name": _normalise(entry.get("title")),
        "sector": "",
        "industry": "",
        "business_summary": "",
        "market_cap": None,
        "exchange": "",
        "cik": cik or None,
    }


def _reset_ticker_index_cache_for_tests() -> None:
    global _TICKER_INDEX_CACHE
    _TICKER_INDEX_CACHE = None
