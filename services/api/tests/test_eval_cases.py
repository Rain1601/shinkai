from __future__ import annotations

import json

from shinkai_api.eval.cases import load_eval_cases, main, run_eval_cases
from shinkai_api.eval.runner import build_eval_report
from shinkai_api.graph.models import Graph
from shinkai_api.runs.models import Run
from shinkai_api.schemas.events import AgentEvent


def test_eval_cases_cover_golden_and_adversarial_paths() -> None:
    result = run_eval_cases()

    assert result.passed
    assert {case.case_id for case in load_eval_cases()} == {
        "golden_source_backed",
        "adversarial_source_gap",
        "adversarial_refute",
        "adversarial_bad_invest_dossier",
    }
    assert all(not case_result.failures for case_result in result.results)


def test_eval_case_cli_outputs_json(capsys) -> None:
    exit_code = main()

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["passed"] is True
    assert {entry["case_id"] for entry in output["results"]} == {
        "golden_source_backed",
        "adversarial_source_gap",
        "adversarial_refute",
        "adversarial_bad_invest_dossier",
    }


def test_eval_runner_handles_event_with_missing_required_field() -> None:
    run = Run(id="r1", mode="mode_b_narrative", anchor="missing-fields-case")
    run.events = [
        AgentEvent(type="supply_chain_layer_started", run_id="r1", data={"layer": "L"}),
        AgentEvent(type="evidence_found", run_id="r1", data={}),
        AgentEvent(type="claim_validated", run_id="r1", data={}),
    ]
    graph = Graph(graph_id="g1", run_id="r1", mode="mode_b_narrative")

    report = build_eval_report(run, graph)

    assert report.evidence_score == 0.0
    assert report.source_quality_score == 0.0


def test_eval_runner_ignores_unknown_extra_fields() -> None:
    run = Run(id="r2", mode="mode_b_narrative", anchor="extra-fields-case")
    run.events = [
        AgentEvent(
            type="evidence_found",
            run_id="r2",
            data={
                "source_backed": True,
                "primary_source_count": 1,
                "source_tiers": ["primary"],
                "future_field_we_do_not_know": "ignored",
            },
        ),
    ]
    graph = Graph(graph_id="g2", run_id="r2", mode="mode_b_narrative")

    report = build_eval_report(run, graph)

    assert report.evidence_score == 0.0  # no evidence nodes yet
    assert report.source_quality_score > 0.0  # backed event scored
