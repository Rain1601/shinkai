from __future__ import annotations

from pydantic import BaseModel, Field


class EvalFinding(BaseModel):
    severity: str
    target_ref: str
    message: str


class EvalReport(BaseModel):
    run_id: str
    process_score: float | None = None
    evidence_score: float | None = None
    reasoning_score: float | None = None
    discovery_score: float | None = None
    claim_score: float | None = None
    source_quality_score: float | None = None
    candidate_dossier_score: float | None = None
    findings: list[EvalFinding] = Field(default_factory=list)
