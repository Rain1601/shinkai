from __future__ import annotations

from collections.abc import Iterable
from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "web",
    "sec",
    "ir",
    "news",
    "filing",
    "transcript",
    "research_report",
    "dataset",
    "manual",
]
EvidenceKind = Literal[
    "quote",
    "summary",
    "metric",
    "filing_fact",
    "transcript_excerpt",
    "web_extract",
]
ClaimStatus = Literal["unsupported", "weak", "supported", "contradicted"]
CandidateStatus = Literal["new", "researching", "qualified", "rejected", "watchlist"]
TaskStatus = Literal["queued", "running", "blocked", "completed", "failed"]


def _unique_ids(values: Iterable[str]) -> set[str]:
    return {value.strip() for value in values if value and value.strip()}


def classify_claim_status(
    supporting_source_ids: Iterable[str],
    contradicting_source_ids: Iterable[str] = (),
    required_independent_sources: int = 2,
) -> ClaimStatus:
    if _unique_ids(contradicting_source_ids):
        return "contradicted"
    support_count = len(_unique_ids(supporting_source_ids))
    if support_count >= max(required_independent_sources, 1):
        return "supported"
    if support_count > 0:
        return "weak"
    return "unsupported"


class SourceRef(BaseModel):
    source_id: str
    type: SourceType = "web"
    url: str
    title: str = ""
    publisher: str = ""
    published_at: float | None = None
    accessed_at: float = Field(default_factory=time)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    run_id: str
    kind: EvidenceKind = "web_extract"
    text: str
    url: str = ""
    quote: str = ""
    summary: str = ""
    published_at: float | None = None
    extracted_at: float = Field(default_factory=time)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supports_claim_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    claim_id: str
    run_id: str
    text: str
    topic: str = ""
    status: ClaimStatus = "unsupported"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    required_independent_sources: int = Field(default=2, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def support_status(
        self,
        supporting_source_ids: Iterable[str],
        contradicting_source_ids: Iterable[str] = (),
    ) -> ClaimStatus:
        return classify_claim_status(
            supporting_source_ids,
            contradicting_source_ids,
            self.required_independent_sources,
        )


class CandidateCompany(BaseModel):
    candidate_id: str
    run_id: str
    name: str
    ticker: str = ""
    sector: str = ""
    supply_chain_layer: str = ""
    thesis: str = ""
    status: CandidateStatus = "new"
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    under_coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchTask(BaseModel):
    task_id: str
    run_id: str
    title: str
    objective: str
    parent_task_id: str | None = None
    status: TaskStatus = "queued"
    assigned_agent: str = "shinkai"
    claim_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time)
    updated_at: float = Field(default_factory=time)
    metadata: dict[str, Any] = Field(default_factory=dict)
