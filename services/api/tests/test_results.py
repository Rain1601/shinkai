from shinkai_api.eval import EvalReport
from shinkai_api.research import CandidateCompany, Claim, CompanyDossier, RunResearchState
from shinkai_api.results import build_published_result
from shinkai_api.runs import Run
from shinkai_api.schemas.events import AgentEvent


def test_published_result_summarizes_research_with_trace_refs() -> None:
    run = Run(
        id="run_result",
        mode="mode_b_narrative",
        anchor="Autonomous Discovery",
        status="completed",
        graph_id="graph_result",
        events=[AgentEvent(type="done", run_id="run_result")],
    )
    research = RunResearchState(
        run_id=run.id,
        claims=[
            Claim(
                claim_id="claim_power",
                run_id=run.id,
                text="Power equipment is a bottleneck.",
                topic="Power",
                status="supported",
                verification="support",
                confidence=0.8,
            )
        ],
        candidates=[
            CandidateCompany(
                candidate_id="cand_vrt",
                run_id=run.id,
                ticker="VRT",
                name="Vertiv",
                supply_chain_layer="Power",
            )
        ],
        dossiers=[
            CompanyDossier(
                dossier_id="dossier_vrt",
                run_id=run.id,
                candidate_id="cand_vrt",
                ticker="VRT",
                company_name="Vertiv",
                supply_chain_layer="Power",
                ai_exposure="Vertiv may benefit from AI data center power density.",
                decision="watch",
                decision_rationale="Watch until primary sources confirm margin impact.",
                claim_ids=["claim_power"],
                evidence_ids=["evidence_power"],
            )
        ],
    )
    eval_report = EvalReport(run_id=run.id, claim_score=0.8, source_quality_score=0.7)

    result = build_published_result(run, research, eval_report)

    assert result.title == "Autonomous Discovery"
    assert result.metrics["claims"] == 1
    assert result.metrics["claim_score"] == 0.8
    assert result.themes == ["Power"]
    assert result.key_findings == ["Power equipment is a bottleneck."]
    assert result.companies[0].trace_refs["claim_ids"] == ["claim_power"]
    assert result.trace_refs["graph_id"] == "graph_result"
