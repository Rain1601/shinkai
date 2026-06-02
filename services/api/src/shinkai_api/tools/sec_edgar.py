"""SEC EDGAR filings tool — primary-source evidence backend.

Once a ticker has been resolved to a CIK by the validator, this tool pulls
the recent 10-K / 10-Q / 8-K filings from the SEC submissions endpoint.
Each filing becomes a ``SourceRef`` with ``tier="primary"`` and a real URL
into EDGAR — which is what shinkai needs to break out of the
``source_quality_score = 0.03`` ceiling.

Reference: https://www.sec.gov/edgar/sec-api-documentation
Rate limit: 10 req/s, must send a real User-Agent header.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from shinkai_api.tools.base import Tool, ToolResult
from shinkai_api.tools.ticker_validator import (
    SEC_USER_AGENT,
    _load_sec_ticker_index,
    _normalise,
)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{document}"

DEFAULT_FORM_TYPES: tuple[str, ...] = ("10-K", "10-Q")


def _pad_cik(cik: str) -> str:
    digits = "".join(ch for ch in cik if ch.isdigit())
    return digits.zfill(10) if digits else ""


def _ticker_to_cik(ticker: str) -> str:
    index = _load_sec_ticker_index()
    entry = index.get(ticker.upper())
    if not entry:
        return ""
    return _pad_cik(str(entry.get("cik_str") or entry.get("cik") or ""))


def _fetch_submissions(cik: str) -> dict[str, Any]:
    request = urllib.request.Request(
        EDGAR_SUBMISSIONS_URL.format(cik=cik),
        headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"EDGAR HTTP {exc.code}: {detail[:200]}") from exc
    return json.loads(raw)


def _extract_filings(
    submissions: dict[str, Any],
    cik: str,
    form_types: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accession_numbers = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    primary_docs = recent.get("primaryDocument") or []
    primary_descs = recent.get("primaryDocDescription") or []

    out: list[dict[str, Any]] = []
    bare_cik = cik.lstrip("0") or cik
    for i, form in enumerate(forms):
        if form not in form_types:
            continue
        accession = _normalise(accession_numbers[i] if i < len(accession_numbers) else "")
        accession_clean = accession.replace("-", "")
        document = _normalise(primary_docs[i] if i < len(primary_docs) else "")
        if not (accession and document):
            continue
        url = EDGAR_FILING_URL.format(
            cik=bare_cik, accession_clean=accession_clean, document=document
        )
        out.append(
            {
                "accession": accession,
                "form": form,
                "filed_at": _normalise(filing_dates[i] if i < len(filing_dates) else ""),
                "period_of_report": _normalise(
                    report_dates[i] if i < len(report_dates) else ""
                ),
                "primary_document_url": url,
                "primary_document_description": _normalise(
                    primary_descs[i] if i < len(primary_descs) else ""
                ),
            }
        )
        if len(out) >= limit:
            break
    return out


class SECFilingsTool(Tool):
    name = "sec_filings"
    description = (
        "Pull recent SEC filings (10-K / 10-Q by default) for a US-listed "
        "ticker and return them as primary-source evidence rows."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "form_types": {
                "type": "array",
                "items": {"type": "string"},
                "default": list(DEFAULT_FORM_TYPES),
            },
            "limit": {"type": "integer", "default": 4},
        },
        "required": ["ticker"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        ticker = _normalise(kwargs.get("ticker")).upper()
        if not ticker:
            return ToolResult(ok=False, error="ticker is required")
        form_types_raw = kwargs.get("form_types") or list(DEFAULT_FORM_TYPES)
        form_types = tuple(str(f).upper() for f in form_types_raw)
        limit = max(1, min(int(kwargs.get("limit") or 4), 12))
        try:
            cik = await asyncio.to_thread(_ticker_to_cik, ticker)
            if not cik:
                return ToolResult(
                    ok=False,
                    error="ticker not found in SEC index",
                    summary=f"no CIK for {ticker}",
                    data={"ticker": ticker, "filings": [], "cik": None},
                )
            submissions = await asyncio.to_thread(_fetch_submissions, cik)
            filings = await asyncio.to_thread(
                _extract_filings, submissions, cik, form_types, limit
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"SEC filings failed for {ticker}",
                data={"ticker": ticker},
            )
        return ToolResult(
            ok=bool(filings),
            summary=(
                f"{ticker}: {len(filings)} filing(s) "
                f"({', '.join(form_types)}) from CIK {cik.lstrip('0')}"
            ),
            data={
                "ticker": ticker,
                "cik": cik,
                "company_name": _normalise(submissions.get("name") or ""),
                "filings": filings,
            },
            error=None if filings else "no matching filings",
        )
