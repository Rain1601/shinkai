from __future__ import annotations

from shinkai_api.research import (
    CandidateCompany,
    Claim,
    Evidence,
    ResearchTask,
    SourceRef,
    classify_claim_status,
)


def test_research_entities_serialize_traceable_refs() -> None:
    source = SourceRef(
        source_id="src_nvidia_10q",
        type="filing",
        url="https://example.com/nvidia-10q",
        title="NVIDIA Form 10-Q",
        publisher="SEC",
        reliability=0.95,
    )
    evidence = Evidence(
        evidence_id="ev_hbm_constraint",
        source_id=source.source_id,
        run_id="run_1",
        kind="filing_fact",
        text="The filing identifies advanced packaging capacity as a supply constraint.",
        confidence=0.82,
        supports_claim_ids=["claim_hbm"],
    )
    claim = Claim(
        claim_id="claim_hbm",
        run_id="run_1",
        topic="AI accelerator supply chain",
        text="HBM and advanced packaging capacity can constrain accelerator supply.",
        evidence_ids=[evidence.evidence_id],
        confidence=0.7,
    )
    candidate = CandidateCompany(
        candidate_id="cand_tsm",
        run_id="run_1",
        ticker="TSM",
        name="Taiwan Semiconductor Manufacturing",
        supply_chain_layer="Advanced packaging",
        thesis="CoWoS capacity is a critical upstream dependency for AI accelerators.",
        claim_ids=[claim.claim_id],
        evidence_ids=[evidence.evidence_id],
        relevance_score=0.9,
    )
    task = ResearchTask(
        task_id="task_deepen_tsm",
        run_id="run_1",
        title="Deepen TSM packaging exposure",
        objective="Validate CoWoS bottleneck exposure with primary sources.",
        candidate_ids=[candidate.candidate_id],
        claim_ids=[claim.claim_id],
        evidence_ids=[evidence.evidence_id],
    )

    payload = task.model_dump()

    assert source.model_dump()["source_id"] == "src_nvidia_10q"
    assert evidence.model_dump()["supports_claim_ids"] == ["claim_hbm"]
    assert payload["candidate_ids"] == ["cand_tsm"]
    assert payload["claim_ids"] == ["claim_hbm"]


def test_claim_status_uses_independent_source_count() -> None:
    assert classify_claim_status([]) == "unsupported"
    assert classify_claim_status(["src_a"]) == "weak"
    assert classify_claim_status(["src_a", "src_b"]) == "supported"
    assert classify_claim_status(["src_a", "src_a"]) == "weak"
    assert classify_claim_status(["src_a", "src_b"], ["src_c"]) == "contradicted"


def test_claim_support_status_respects_claim_threshold() -> None:
    claim = Claim(
        claim_id="claim_power",
        run_id="run_1",
        text="Power equipment is an AI data center bottleneck.",
        required_independent_sources=3,
    )

    assert claim.support_status(["src_a", "src_b"]) == "weak"
    assert claim.support_status(["src_a", "src_b", "src_c"]) == "supported"
    assert claim.support_status(["src_a", "src_b", "src_c"], ["src_d"]) == "contradicted"
