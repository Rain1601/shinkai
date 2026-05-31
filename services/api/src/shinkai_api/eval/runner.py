from __future__ import annotations

from shinkai_api.eval.models import EvalFinding, EvalReport
from shinkai_api.graph.models import Graph
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

    return EvalReport(
        run_id=run.id,
        process_score=process_score,
        evidence_score=evidence_score,
        reasoning_score=reasoning_score,
        discovery_score=discovery_score,
        findings=findings,
    )


def _bounded_score(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 3)
