from __future__ import annotations

import asyncio

import pytest

from shinkai_api.tools.sec_edgar import (
    SECFilingsTool,
    _extract_filings,
    _pad_cik,
)


def test_pad_cik_pads_to_ten_digits() -> None:
    assert _pad_cik("1045810") == "0001045810"
    assert _pad_cik("CIK0000789019") == "0000789019"


def test_extract_filings_picks_only_requested_forms() -> None:
    submissions = {
        "name": "Test Corp",
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q", "10-Q", "4"],
                "accessionNumber": [
                    "0001234567-26-000001",
                    "0001234567-26-000002",
                    "0001234567-26-000003",
                    "0001234567-26-000004",
                    "0001234567-26-000005",
                ],
                "filingDate": [
                    "2026-02-15",
                    "2026-02-20",
                    "2026-04-30",
                    "2026-08-01",
                    "2026-01-10",
                ],
                "reportDate": ["2025-12-31", "", "2026-03-31", "2026-06-30", ""],
                "primaryDocument": ["10k.htm", "8k.htm", "10q1.htm", "10q2.htm", "form4.htm"],
                "primaryDocDescription": ["Annual report", "", "Quarterly", "Quarterly", ""],
            }
        },
    }
    filings = _extract_filings(
        submissions, "0000123456", ("10-K", "10-Q"), limit=4
    )
    assert len(filings) == 3
    assert {f["form"] for f in filings} == {"10-K", "10-Q"}
    first = filings[0]
    assert first["accession"] == "0001234567-26-000001"
    assert "123456" in first["primary_document_url"]
    assert "10k.htm" in first["primary_document_url"]


def test_sec_tool_returns_error_for_unknown_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shinkai_api.tools.sec_edgar._ticker_to_cik", lambda ticker: ""
    )
    tool = SECFilingsTool()
    result = asyncio.run(tool.run(ticker="ZZZZZ"))
    assert result.ok is False
    assert result.data["filings"] == []


def test_sec_tool_normalises_filings_from_submissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shinkai_api.tools.sec_edgar._ticker_to_cik", lambda ticker: "0001045810"
    )
    monkeypatch.setattr(
        "shinkai_api.tools.sec_edgar._fetch_submissions",
        lambda cik: {
            "name": "NVIDIA CORP",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q"],
                    "accessionNumber": [
                        "0001045810-26-000001",
                        "0001045810-26-000002",
                    ],
                    "filingDate": ["2026-02-22", "2026-05-29"],
                    "reportDate": ["2026-01-26", "2026-04-27"],
                    "primaryDocument": ["nvda-10k.htm", "nvda-10q.htm"],
                    "primaryDocDescription": ["10-K", "10-Q"],
                }
            },
        },
    )
    tool = SECFilingsTool()
    result = asyncio.run(tool.run(ticker="NVDA"))
    assert result.ok is True
    assert result.data["company_name"] == "NVIDIA CORP"
    assert len(result.data["filings"]) == 2
    assert "nvda-10k.htm" in result.data["filings"][0]["primary_document_url"]
