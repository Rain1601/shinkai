from __future__ import annotations

from shinkai_api.agent.personas import (
    AUDITOR_PROMPT,
    BUFFETT_PROMPT,
    SHORT_SELLER_PROMPT,
    build_critique,
)
from shinkai_api.agent.personas.runner import aggregate_critiques


def test_persona_prompts_are_distinct_and_substantive() -> None:
    assert "Buffett-school" in BUFFETT_PROMPT
    assert "short-seller" in SHORT_SELLER_PROMPT
    assert "forensic auditor" in AUDITOR_PROMPT
    assert len(BUFFETT_PROMPT) > 200
    assert len(SHORT_SELLER_PROMPT) > 200
    assert len(AUDITOR_PROMPT) > 200


def test_aggregate_critiques_rejects_when_any_reject() -> None:
    critiques = [
        build_critique("buffett", verdict="endorse", rationale="moat"),
        build_critique("short_seller", verdict="reject", rationale="concentration risk"),
        build_critique("auditor", verdict="endorse", rationale="sources OK"),
    ]

    result = aggregate_critiques(critiques)

    assert result["final"] == "reject"
    assert result["vote_summary"] == {"endorse": 2, "concerns": 0, "reject": 1}


def test_aggregate_critiques_majority_endorse() -> None:
    critiques = [
        build_critique("buffett", verdict="endorse", rationale="moat"),
        build_critique("short_seller", verdict="concerns", rationale="watch revenue mix"),
        build_critique("auditor", verdict="endorse", rationale="sources OK"),
    ]

    result = aggregate_critiques(critiques)

    assert result["final"] == "endorse"
    assert result["vote_summary"]["endorse"] == 2


def test_aggregate_critiques_no_majority_returns_concerns() -> None:
    critiques = [
        build_critique("buffett", verdict="concerns", rationale="moat unclear"),
        build_critique("short_seller", verdict="concerns", rationale="risks present"),
        build_critique("auditor", verdict="endorse", rationale="sources OK"),
    ]

    result = aggregate_critiques(critiques)

    assert result["final"] == "concerns"


def test_aggregate_critiques_handles_empty_list() -> None:
    result = aggregate_critiques([])

    assert result["final"] == "concerns"
    assert result["critiques"] == []
