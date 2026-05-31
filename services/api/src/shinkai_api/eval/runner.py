from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shinkai_api.eval.models import EvalFinding, EvalReport
from shinkai_api.graph.models import Graph, Node
from shinkai_api.runs.models import Run


def build_eval_report(run: Run, graph: Graph) -> EvalReport:
    event_types = [event.type for event in run.events]
    findings: list[EvalFinding] = []

    layers = event_types.count("supply_chain_layer_started")
    candidates = event_types.count("candidate_scored")
    reviews = event_types.count("review_completed")
    optimizations = event_types.count("optimization_decision")
    patches = sum(1 for event_type in event_types if str(event_type).endswith("_patch_proposed"))

    evidence_nodes = [node for node in graph.nodes if node.type == "Evidence"]
    source_backed = [node for node in evidence_nodes if "source-backed" in node.tags]
    claims = [node for node in graph.nodes if node.type == "Claim"]
    candidate_claims = [node for node in graph.nodes if "candidate-claim" in node.tags]
    questions = [node for node in graph.nodes if node.type == "Question"]
    theses = [node for node in graph.nodes if node.type == "Thesis"]
    claim_payloads = _claim_payloads(claims)
    evidence_events = [event for event in run.events if event.type == "evidence_found"]
    dossier_events = [event for event in run.events if event.type == "company_dossier_created"]

    if not layers:
        findings.append(
            EvalFinding(
                severity="error",
                target_ref=run.id,
                message="No supply-chain layer was expanded.",
            )
        )
    if candidates < max(1, layers * 2):
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.id,
                message="Candidate coverage is thin for the expanded frontier count.",
            )
        )
    if len(source_backed) < len(evidence_nodes):
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message="Some evidence nodes still need source-backed verification.",
            )
        )
    if patches < layers:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.id,
                message="Not every loop produced a self-iteration patch proposal.",
            )
        )
    if candidates and len(candidate_claims) < candidates:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message="Not every scored candidate has a candidate claim node.",
            )
        )
    if candidates and len(questions) < candidates:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message="Not every scored candidate has an open underwriting question.",
            )
        )
    if not theses:
        findings.append(
            EvalFinding(
                severity="info",
                target_ref=run.graph_id or run.id,
                message="No candidate has been promoted to an initial thesis yet.",
            )
        )
    if claims and len(claim_payloads) < len(claims):
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message="Some claim nodes are missing verification metadata.",
            )
        )
    unsupported_claims = [
        claim
        for claim in claim_payloads
        if str(claim.get("verification") or "") == "insufficient"
    ]
    if unsupported_claims:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message=f"{len(unsupported_claims)} claims lack sufficient source support.",
            )
        )
    primary_gaps = [
        claim
        for claim in claim_payloads
        if str(claim.get("verification") or "") == "support"
        and _number(claim.get("primary_source_count")) <= 0
    ]
    if primary_gaps:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message=f"{len(primary_gaps)} supported claims still lack a primary source.",
            )
        )
    contradicted_claims = [
        claim for claim in claim_payloads if str(claim.get("verification") or "") == "refute"
    ]
    if contradicted_claims:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message=f"{len(contradicted_claims)} claims have refuting evidence.",
            )
        )
    stale_claims = [
        claim
        for claim in claim_payloads
        if str(claim.get("verification") or "") == "stale" or claim.get("stale_source_ids")
    ]
    if stale_claims:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message=f"{len(stale_claims)} claims depend on stale sources.",
            )
        )
    if evidence_events and not any(
        _number(_payload(event).get("primary_source_count")) > 0 for event in evidence_events
    ):
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.graph_id or run.id,
                message="The run found evidence but no primary-source-backed evidence.",
            )
        )
    if candidates and len(dossier_events) < candidates:
        findings.append(
            EvalFinding(
                severity="warning",
                target_ref=run.id,
                message="Not every scored candidate has a company dossier.",
            )
        )
    invest_without_checks = [
        event
        for event in dossier_events
        if _payload(event).get("decision") == "invest"
        and not _all_mode_a_checks_pass(_payload(event).get("mode_a_checks"))
    ]
    if invest_without_checks:
        findings.append(
            EvalFinding(
                severity="error",
                target_ref=run.id,
                message="At least one investment decision was made without passing Mode A checks.",
            )
        )

    process_score = _bounded_score(
        (layers > 0) * 0.3 + (reviews > 0) * 0.3 + (optimizations > 0) * 0.4
    )
    evidence_score = _bounded_score(len(source_backed) / max(1, len(evidence_nodes)))
    reasoning_score = _bounded_score(
        (len(claims) / max(1, layers)) * 0.35
        + (reviews / max(1, layers)) * 0.35
        + (patches / max(1, layers * 3)) * 0.3
    )
    discovery_score = _bounded_score(
        min(1.0, candidates / max(1, layers * 3)) * 0.45
        + min(1.0, len(candidate_claims) / max(1, candidates)) * 0.25
        + min(1.0, len(questions) / max(1, candidates)) * 0.2
        + min(1.0, len(theses) / max(1, layers)) * 0.1
    )
    claim_score = _claim_score(claims, claim_payloads)
    source_quality_score = _source_quality_score(evidence_events, evidence_score)
    candidate_dossier_score = _candidate_dossier_score(dossier_events, candidates)

    return EvalReport(
        run_id=run.id,
        process_score=process_score,
        evidence_score=evidence_score,
        reasoning_score=reasoning_score,
        discovery_score=discovery_score,
        claim_score=claim_score,
        source_quality_score=source_quality_score,
        candidate_dossier_score=candidate_dossier_score,
        findings=findings,
    )


def _bounded_score(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 3)


def _payload(event: Any) -> Mapping[str, Any]:
    data = getattr(event, "data", {})
    return data if isinstance(data, Mapping) else {}


def _claim_payloads(claims: list[Node]) -> list[Mapping[str, Any]]:
    return [
        node.data
        for node in claims
        if node.data.get("status") or node.data.get("verification")
    ]


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _claim_score(claims: list[Node], claim_payloads: list[Mapping[str, Any]]) -> float:
    if not claims:
        return 0.0
    total = max(1, len(claims))
    scored_total = max(1, len(claim_payloads))
    verified_ratio = min(1.0, len(claim_payloads) / total)
    supported_ratio = sum(
        1 for claim in claim_payloads if claim.get("verification") == "support"
    ) / scored_total
    primary_ratio = sum(
        1 for claim in claim_payloads if _number(claim.get("primary_source_count")) > 0
    ) / scored_total
    risk_ratio = sum(
        1
        for claim in claim_payloads
        if claim.get("verification") in {"refute", "insufficient", "stale"}
        or bool(claim.get("stale_source_ids"))
    ) / scored_total
    return _bounded_score(
        verified_ratio * 0.2
        + supported_ratio * 0.35
        + primary_ratio * 0.25
        + (1 - risk_ratio) * 0.2
    )


def _source_quality_score(evidence_events: list[Any], evidence_score: float) -> float:
    if not evidence_events:
        return evidence_score
    total = max(1, len(evidence_events))
    backed_ratio = sum(
        1 for event in evidence_events if bool(_payload(event).get("source_backed"))
    ) / total
    primary_ratio = sum(
        1 for event in evidence_events if _number(_payload(event).get("primary_source_count")) > 0
    ) / total
    tier_score = sum(_tier_score(_payload(event).get("source_tiers")) for event in evidence_events)
    return _bounded_score(backed_ratio * 0.35 + primary_ratio * 0.35 + tier_score / total * 0.3)


def _tier_score(value: object) -> float:
    if not isinstance(value, list) or not value:
        return 0.0
    weights = {
        "primary": 1.0,
        "secondary": 0.65,
        "tertiary": 0.35,
        "agent_inference": 0.1,
    }
    scores = [weights.get(str(item), 0.0) for item in value]
    return sum(scores) / max(1, len(scores))


def _candidate_dossier_score(dossier_events: list[Any], candidate_count: int) -> float:
    if candidate_count <= 0:
        return 0.0
    total = max(1, len(dossier_events))
    coverage_ratio = min(1.0, len(dossier_events) / candidate_count)
    decision_ratio = sum(
        1
        for event in dossier_events
        if _payload(event).get("decision") in {"invest", "watch", "reject"}
    ) / total
    rationale_ratio = sum(
        1 for event in dossier_events if bool(str(_payload(event).get("decision_rationale") or ""))
    ) / total
    checks_ratio = sum(
        1 for event in dossier_events if _has_mode_a_checks(_payload(event).get("mode_a_checks"))
    ) / total
    consistency_ratio = sum(
        1
        for event in dossier_events
        if _payload(event).get("decision") != "invest"
        or _all_mode_a_checks_pass(_payload(event).get("mode_a_checks"))
    ) / total
    return _bounded_score(
        coverage_ratio * 0.35
        + checks_ratio * 0.2
        + rationale_ratio * 0.2
        + decision_ratio * 0.15
        + consistency_ratio * 0.1
    )


def _has_mode_a_checks(value: object) -> bool:
    return isinstance(value, Mapping) and bool(value)


def _all_mode_a_checks_pass(value: object) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(bool(item) for item in value.values())
