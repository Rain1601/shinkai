from __future__ import annotations

from collections.abc import Iterable
from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceTier = Literal["primary", "secondary", "tertiary", "agent_inference"]
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
ClaimVerification = Literal["support", "refute", "insufficient", "stale"]
CandidateStatus = Literal["new", "researching", "qualified", "rejected", "watchlist"]
TaskStatus = Literal["queued", "running", "blocked", "completed", "failed"]
InvestmentDecision = Literal["invest", "watch", "reject"]


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


def classify_source_tier(
    source_type: SourceType,
    url: str = "",
    publisher: str = "",
) -> SourceTier:
    url_lower = url.lower()
    publisher_lower = publisher.lower()
    if source_type == "manual":
        return "agent_inference"
    if source_type in {"sec", "filing", "transcript", "ir", "dataset"}:
        return "primary"
    if "sec.gov" in url_lower or "investor" in url_lower or "ir." in url_lower:
        return "primary"
    if source_type in {"news", "research_report"}:
        return "secondary"
    if any(name in publisher_lower for name in ["reuters", "bloomberg", "wsj", "ft.com"]):
        return "secondary"
    return "tertiary"


def source_reliability_score(tier: SourceTier, extracted: bool = False) -> float:
    base = {
        "primary": 0.9,
        "secondary": 0.72,
        "tertiary": 0.56,
        "agent_inference": 0.2,
    }[tier]
    return min(1.0, base + (0.05 if extracted and tier != "agent_inference" else 0.0))


class SourceRef(BaseModel):
    source_id: str
    type: SourceType = "web"
    tier: SourceTier = "tertiary"
    url: str
    title: str = ""
    publisher: str = ""
    # POSIX timestamp in seconds (UTC), or None when publication date is unknown.
    published_at: float | None = None
    primary_source_flag: bool = False
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
    citation_url: str = ""
    citation_anchor: str = ""
    citation_label: str = ""
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
    verification: ClaimVerification = "insufficient"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    stale_evidence_ids: list[str] = Field(default_factory=list)
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


class ClaimAssessment(BaseModel):
    status: ClaimStatus
    verification: ClaimVerification
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    independent_source_count: int = 0
    primary_source_count: int = 0
    contradicting_source_count: int = 0
    stale_source_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


def assess_claim_support(
    supporting_sources: Iterable[SourceRef],
    contradicting_sources: Iterable[SourceRef] = (),
    *,
    required_independent_sources: int = 2,
    now: float | None = None,
    max_source_age_days: int = 730,
) -> ClaimAssessment:
    support = list(supporting_sources)
    contradict = list(contradicting_sources)
    current_time = time() if now is None else now
    max_age_seconds = max_source_age_days * 24 * 60 * 60
    stale_source_ids = [
        source.source_id
        for source in support
        if source.published_at is not None and current_time - source.published_at > max_age_seconds
    ]
    fresh_support = [source for source in support if source.source_id not in stale_source_ids]
    independent_ids = _unique_ids(source.source_id for source in fresh_support)
    primary_count = len(
        _unique_ids(
            source.source_id
            for source in fresh_support
            if source.tier == "primary" or source.primary_source_flag
        )
    )
    contradiction_count = len(_unique_ids(source.source_id for source in contradict))
    primary_contradictions = [
        source for source in contradict if source.tier == "primary" or source.primary_source_flag
    ]
    contradiction_reliability = _average_reliability(contradict)
    support_reliability = _average_reliability(fresh_support) if fresh_support else 0.0
    contradiction_is_decisive = (
        bool(primary_contradictions)
        or contradiction_count >= 2
        or (not fresh_support and contradiction_count >= 1)
        or contradiction_reliability >= support_reliability + 0.15
    )
    if contradiction_count and contradiction_is_decisive:
        return ClaimAssessment(
            status="contradicted",
            verification="refute",
            confidence=contradiction_reliability,
            independent_source_count=len(independent_ids),
            primary_source_count=primary_count,
            contradicting_source_count=contradiction_count,
            stale_source_ids=stale_source_ids,
            rationale="contradicting evidence is primary, replicated, or outweighs support",
        )
    if contradiction_count:
        return ClaimAssessment(
            status="weak",
            verification="insufficient",
            confidence=max(0.0, support_reliability - 0.15 * contradiction_count),
            independent_source_count=len(independent_ids),
            primary_source_count=primary_count,
            contradicting_source_count=contradiction_count,
            stale_source_ids=stale_source_ids,
            rationale=(
                "weak contradicting signal present but does not outweigh existing support"
            ),
        )
    if stale_source_ids and not fresh_support:
        return ClaimAssessment(
            status="unsupported",
            verification="stale",
            confidence=0.0,
            independent_source_count=0,
            primary_source_count=0,
            stale_source_ids=stale_source_ids,
            rationale="all supporting evidence is stale",
        )
    if len(independent_ids) >= max(required_independent_sources, 1) and primary_count > 0:
        return ClaimAssessment(
            status="supported",
            verification="support",
            confidence=_average_reliability(fresh_support),
            independent_source_count=len(independent_ids),
            primary_source_count=primary_count,
            stale_source_ids=stale_source_ids,
            rationale="enough independent evidence including a primary source",
        )
    if independent_ids:
        return ClaimAssessment(
            status="weak",
            verification="insufficient",
            confidence=_average_reliability(fresh_support) * 0.75,
            independent_source_count=len(independent_ids),
            primary_source_count=primary_count,
            stale_source_ids=stale_source_ids,
            rationale="supporting evidence exists but does not meet source-quality threshold",
        )
    return ClaimAssessment(
        status="unsupported",
        verification="insufficient",
        rationale="no supporting evidence",
    )


def _average_reliability(sources: Iterable[SourceRef]) -> float:
    scores = [source.reliability for source in sources]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 3)


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


class CompanyDossier(BaseModel):
    dossier_id: str
    run_id: str
    candidate_id: str
    ticker: str
    company_name: str
    supply_chain_layer: str = ""
    business_summary: str = ""
    ai_exposure: str = ""
    supply_chain_position: str = ""
    financial_metrics: dict[str, float | str | None] = Field(default_factory=dict)
    valuation_view: str = ""
    risk_factors: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    mode_a_checks: dict[str, bool] = Field(default_factory=dict)
    decision: InvestmentDecision = "watch"
    decision_rationale: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time)
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


class RunResearchState(BaseModel):
    run_id: str
    sources: list[SourceRef] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    candidates: list[CandidateCompany] = Field(default_factory=list)
    dossiers: list[CompanyDossier] = Field(default_factory=list)
    tasks: list[ResearchTask] = Field(default_factory=list)
