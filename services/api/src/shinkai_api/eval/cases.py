from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from shinkai_api.eval.models import EvalReport
from shinkai_api.eval.runner import build_eval_report
from shinkai_api.graph.models import Graph, Node
from shinkai_api.runs.models import Run
from shinkai_api.schemas.events import AgentEvent

ScoreName = Literal[
    "process_score",
    "evidence_score",
    "reasoning_score",
    "discovery_score",
    "claim_score",
    "source_quality_score",
    "candidate_dossier_score",
]


class EvalCaseExpectation(BaseModel):
    min_scores: dict[ScoreName, float] = Field(default_factory=dict)
    max_scores: dict[ScoreName, float] = Field(default_factory=dict)
    required_findings: list[str] = Field(default_factory=list)
    forbidden_findings: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    case_id: str
    description: str
    run: Run
    graph: Graph
    expectation: EvalCaseExpectation


class EvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    scores: dict[str, float | None] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)


class EvalSuiteResult(BaseModel):
    passed: bool
    results: list[EvalCaseResult]


def load_eval_cases() -> list[EvalCase]:
    return [
        _make_case(
            case_id="golden_source_backed",
            description="Supported claims with primary evidence and complete dossiers pass.",
            verification="support",
            source_backed=True,
            primary_source_count=1,
            source_tiers=["primary"],
            candidate_count=2,
            dossier_decision="invest",
            mode_a_checks={
                "quality": True,
                "undercovered": True,
                "direct_ai_exposure": True,
                "margin_accretive": True,
                "valuation_reasonable": True,
                "risk_not_refuted": True,
            },
            expectation=EvalCaseExpectation(
                min_scores={
                    "process_score": 1.0,
                    "evidence_score": 1.0,
                    "claim_score": 1.0,
                    "source_quality_score": 1.0,
                    "candidate_dossier_score": 1.0,
                },
                forbidden_findings=["warning", "error"],
            ),
        ),
        _make_case(
            case_id="adversarial_source_gap",
            description="Agent-inference-only evidence should stay low quality.",
            verification="insufficient",
            source_backed=False,
            primary_source_count=0,
            source_tiers=["agent_inference"],
            candidate_count=2,
            dossier_decision="watch",
            mode_a_checks={
                "quality": True,
                "undercovered": True,
                "direct_ai_exposure": False,
                "margin_accretive": False,
                "valuation_reasonable": True,
                "risk_not_refuted": True,
            },
            expectation=EvalCaseExpectation(
                max_scores={
                    "evidence_score": 0.0,
                    "claim_score": 0.3,
                    "source_quality_score": 0.05,
                },
                required_findings=[
                    "lack sufficient source support",
                    "no primary-source-backed evidence",
                ],
            ),
        ),
        _make_case(
            case_id="adversarial_refute",
            description="Refuting evidence should cap claim confidence and surface a finding.",
            verification="refute",
            source_backed=True,
            primary_source_count=1,
            source_tiers=["primary"],
            candidate_count=2,
            dossier_decision="reject",
            mode_a_checks={
                "quality": True,
                "undercovered": True,
                "direct_ai_exposure": False,
                "margin_accretive": True,
                "valuation_reasonable": True,
                "risk_not_refuted": False,
            },
            expectation=EvalCaseExpectation(
                max_scores={"claim_score": 0.55},
                required_findings=["refuting evidence"],
            ),
        ),
        _make_case(
            case_id="adversarial_bad_invest_dossier",
            description="Invest decisions require every Mode A check to pass.",
            verification="support",
            source_backed=True,
            primary_source_count=1,
            source_tiers=["primary"],
            candidate_count=1,
            dossier_decision="invest",
            mode_a_checks={
                "quality": True,
                "undercovered": True,
                "direct_ai_exposure": True,
                "margin_accretive": False,
                "valuation_reasonable": True,
                "risk_not_refuted": True,
            },
            expectation=EvalCaseExpectation(
                max_scores={"candidate_dossier_score": 0.9},
                required_findings=["without passing Mode A checks"],
            ),
        ),
    ]


def run_eval_cases(cases: Iterable[EvalCase] | None = None) -> EvalSuiteResult:
    results = [_run_eval_case(case) for case in cases or load_eval_cases()]
    return EvalSuiteResult(passed=all(result.passed for result in results), results=results)


def main() -> int:
    result = run_eval_cases()
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.passed else 1


def _run_eval_case(case: EvalCase) -> EvalCaseResult:
    report = build_eval_report(case.run, case.graph)
    failures = _check_expectation(report, case.expectation)
    return EvalCaseResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
        scores=_score_snapshot(report),
        findings=[finding.message for finding in report.findings],
    )


def _check_expectation(report: EvalReport, expectation: EvalCaseExpectation) -> list[str]:
    failures: list[str] = []
    for name, minimum in expectation.min_scores.items():
        value = getattr(report, name)
        if value is None or value < minimum:
            failures.append(f"{name} expected >= {minimum}, got {value}")
    for name, maximum in expectation.max_scores.items():
        value = getattr(report, name)
        if value is None or value > maximum:
            failures.append(f"{name} expected <= {maximum}, got {value}")

    finding_text = "\n".join(
        f"{finding.severity}: {finding.message}" for finding in report.findings
    )
    for expected in expectation.required_findings:
        if expected not in finding_text:
            failures.append(f"missing finding containing: {expected}")
    for forbidden in expectation.forbidden_findings:
        if forbidden in finding_text:
            failures.append(f"unexpected finding containing: {forbidden}")
    return failures


def _score_snapshot(report: EvalReport) -> dict[str, float | None]:
    return {
        "process_score": report.process_score,
        "evidence_score": report.evidence_score,
        "reasoning_score": report.reasoning_score,
        "discovery_score": report.discovery_score,
        "claim_score": report.claim_score,
        "source_quality_score": report.source_quality_score,
        "candidate_dossier_score": report.candidate_dossier_score,
    }


def _make_case(
    *,
    case_id: str,
    description: str,
    verification: str,
    source_backed: bool,
    primary_source_count: int,
    source_tiers: list[str],
    candidate_count: int,
    dossier_decision: str,
    mode_a_checks: dict[str, bool],
    expectation: EvalCaseExpectation,
) -> EvalCase:
    run_id = f"eval_{case_id}"
    graph_id = f"graph_{case_id}"
    run = Run(
        id=run_id,
        mode="mode_b_narrative",
        anchor=case_id,
        status="completed",
        lifecycle_stage="completed",
        graph_id=graph_id,
        events=_events(
            run_id=run_id,
            verification=verification,
            source_backed=source_backed,
            primary_source_count=primary_source_count,
            source_tiers=source_tiers,
            candidate_count=candidate_count,
            dossier_decision=dossier_decision,
            mode_a_checks=mode_a_checks,
        ),
    )
    graph = Graph(
        graph_id=graph_id,
        run_id=run_id,
        mode="mode_b_narrative",
        nodes=_nodes(
            verification=verification,
            source_backed=source_backed,
            primary_source_count=primary_source_count,
            candidate_count=candidate_count,
        ),
        edges=[],
    )
    return EvalCase(
        case_id=case_id,
        description=description,
        run=run,
        graph=graph,
        expectation=expectation,
    )


def _events(
    *,
    run_id: str,
    verification: str,
    source_backed: bool,
    primary_source_count: int,
    source_tiers: list[str],
    candidate_count: int,
    dossier_decision: str,
    mode_a_checks: dict[str, bool],
) -> list[AgentEvent]:
    events = [
        AgentEvent(type="supply_chain_layer_started", run_id=run_id, data={"layer": "Eval layer"}),
        AgentEvent(
            type="evidence_found",
            run_id=run_id,
            data={
                "source_backed": source_backed,
                "source_tiers": source_tiers,
                "primary_source_count": primary_source_count,
            },
        ),
        AgentEvent(
            type="claim_validated",
            run_id=run_id,
            data={
                "verification": verification,
                "status": _claim_status(verification),
                "primary_source_count": primary_source_count,
                "stale_source_ids": [],
            },
        ),
        AgentEvent(type="review_completed", run_id=run_id, data={"review_score": 0.8}),
        AgentEvent(
            type="optimization_decision",
            run_id=run_id,
            data={"decision": "continue_deeper"},
        ),
        AgentEvent(type="memory_patch_proposed", run_id=run_id, data={}),
        AgentEvent(type="filter_policy_patch_proposed", run_id=run_id, data={}),
        AgentEvent(type="checklist_patch_proposed", run_id=run_id, data={}),
    ]
    for index in range(candidate_count):
        events.append(
            AgentEvent(
                type="candidate_scored",
                run_id=run_id,
                data={"ticker": f"EV{index}", "combined_score": 0.7},
            )
        )
        events.append(
            AgentEvent(
                type="company_dossier_created",
                run_id=run_id,
                data={
                    "ticker": f"EV{index}",
                    "decision": dossier_decision,
                    "decision_rationale": "Synthetic eval decision.",
                    "mode_a_checks": mode_a_checks,
                },
            )
        )
    return events


def _nodes(
    *,
    verification: str,
    source_backed: bool,
    primary_source_count: int,
    candidate_count: int,
) -> list[Node]:
    tags = ["source-backed"] if source_backed else []
    nodes = [
        Node(id="evidence_eval", type="Evidence", tags=tags),
        _claim_node(
            "claim_bottleneck",
            verification=verification,
            primary_source_count=primary_source_count,
            tags=["bottleneck"],
        ),
    ]
    for index in range(candidate_count):
        nodes.extend(
            [
                _claim_node(
                    f"claim_candidate_{index}",
                    verification=verification,
                    primary_source_count=primary_source_count,
                    tags=["candidate-claim"],
                ),
                Node(id=f"question_{index}", type="Question"),
            ]
        )
    if verification == "support":
        nodes.append(Node(id="thesis_eval", type="Thesis"))
    return nodes


def _claim_node(
    node_id: str,
    *,
    verification: str,
    primary_source_count: int,
    tags: list[str],
) -> Node:
    return Node(
        id=node_id,
        type="Claim",
        data={
            "verification": verification,
            "status": _claim_status(verification),
            "primary_source_count": primary_source_count,
            "stale_source_ids": [],
        },
        tags=tags,
    )


def _claim_status(verification: str) -> str:
    return {
        "support": "supported",
        "refute": "contradicted",
        "stale": "weak",
        "insufficient": "unsupported",
    }.get(verification, "unsupported")


if __name__ == "__main__":
    raise SystemExit(main())
