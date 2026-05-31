from __future__ import annotations

from time import time
from typing import Any

from pydantic import BaseModel, Field

from shinkai_api.eval import EvalReport
from shinkai_api.research import CompanyDossier, RunResearchState
from shinkai_api.runs import Run


class PublishedCompany(BaseModel):
    ticker: str
    name: str
    layer: str
    decision: str
    decision_rationale: str
    thesis: str
    risk_factors: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    trace_refs: dict[str, Any] = Field(default_factory=dict)


class PublishedResult(BaseModel):
    run_id: str
    graph_id: str | None = None
    title: str
    status: str
    generated_at: float = Field(default_factory=time)
    summary: str
    themes: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    companies: list[PublishedCompany] = Field(default_factory=list)
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    trace_refs: dict[str, Any] = Field(default_factory=dict)


def build_published_result(
    run: Run,
    research: RunResearchState,
    eval_report: EvalReport | None = None,
) -> PublishedResult:
    themes = _themes(research)
    key_findings = _key_findings(research)
    companies = [_published_company(dossier) for dossier in _ranked_dossiers(research.dossiers)]
    metrics: dict[str, float | int | str | None] = {
        "sources": len(research.sources),
        "claims": len(research.claims),
        "candidates": len(research.candidates),
        "dossiers": len(research.dossiers),
        "tasks": len(research.tasks),
        "events": len(run.events),
    }
    if eval_report is not None:
        metrics.update(
            {
                "process_score": eval_report.process_score,
                "evidence_score": eval_report.evidence_score,
                "claim_score": eval_report.claim_score,
                "source_quality_score": eval_report.source_quality_score,
                "candidate_dossier_score": eval_report.candidate_dossier_score,
            }
        )
    return PublishedResult(
        run_id=run.id,
        graph_id=run.graph_id,
        title=run.anchor,
        status=run.status,
        summary=_summary(run, themes, companies, metrics),
        themes=themes,
        key_findings=key_findings,
        companies=companies,
        metrics=metrics,
        trace_refs={
            "run_id": run.id,
            "graph_id": run.graph_id,
            "event_count": len(run.events),
            "research_counts": {
                "sources": len(research.sources),
                "claims": len(research.claims),
                "candidates": len(research.candidates),
                "dossiers": len(research.dossiers),
            },
        },
    )


def _themes(research: RunResearchState) -> list[str]:
    values = {
        *[candidate.supply_chain_layer for candidate in research.candidates],
        *[claim.topic for claim in research.claims],
    }
    return [value for value in sorted(values) if value][:8]


def _key_findings(research: RunResearchState) -> list[str]:
    ranked = sorted(
        research.claims,
        key=lambda claim: (
            claim.verification != "support",
            claim.status != "supported",
            -claim.confidence,
        ),
    )
    return [claim.text for claim in ranked if claim.text][:6]


def _ranked_dossiers(dossiers: list[CompanyDossier]) -> list[CompanyDossier]:
    decision_rank = {"invest": 0, "watch": 1, "reject": 2}
    return sorted(
        dossiers,
        key=lambda dossier: (
            decision_rank.get(dossier.decision, 3),
            dossier.supply_chain_layer,
            dossier.ticker,
        ),
    )[:12]


def _published_company(dossier: CompanyDossier) -> PublishedCompany:
    return PublishedCompany(
        ticker=dossier.ticker,
        name=dossier.company_name,
        layer=dossier.supply_chain_layer,
        decision=dossier.decision,
        decision_rationale=dossier.decision_rationale,
        thesis=dossier.ai_exposure,
        risk_factors=dossier.risk_factors[:4],
        catalysts=dossier.catalysts[:4],
        trace_refs={
            "dossier_id": dossier.dossier_id,
            "candidate_id": dossier.candidate_id,
            "claim_ids": dossier.claim_ids,
            "evidence_ids": dossier.evidence_ids,
        },
    )


def _summary(
    run: Run,
    themes: list[str],
    companies: list[PublishedCompany],
    metrics: dict[str, float | int | str | None],
) -> str:
    return (
        f"{run.anchor} produced {len(themes)} themes, "
        f"{metrics['claims']} claims, and {len(companies)} company dossiers."
    )
