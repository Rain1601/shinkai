from __future__ import annotations

from shinkai_api.research import (
    CandidateCompany,
    Claim,
    Evidence,
    ResearchTask,
    SourceRef,
    assess_claim_support,
    classify_claim_status,
    classify_source_tier,
    source_reliability_score,
)


def test_research_entities_serialize_traceable_refs() -> None:
    source = SourceRef(
        source_id="src_nvidia_10q",
        type="filing",
        tier="primary",
        url="https://example.com/nvidia-10q",
        title="NVIDIA Form 10-Q",
        publisher="SEC",
        primary_source_flag=True,
        reliability=0.95,
    )
    evidence = Evidence(
        evidence_id="ev_hbm_constraint",
        source_id=source.source_id,
        run_id="run_1",
        kind="filing_fact",
        text="The filing identifies advanced packaging capacity as a supply constraint.",
        quote="advanced packaging capacity as a supply constraint",
        citation_url="https://example.com/nvidia-10q",
        citation_anchor="risk-factors",
        citation_label="Form 10-Q risk factors",
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
    assert source.tier == "primary"
    assert source.primary_source_flag is True
    assert evidence.citation_anchor == "risk-factors"
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


def test_source_tier_and_reliability_helpers() -> None:
    assert (
        classify_source_tier("filing", "https://www.sec.gov/Archives/form-10q", "SEC")
        == "primary"
    )
    assert classify_source_tier("news", "https://www.reuters.com/article", "Reuters") == "secondary"
    assert classify_source_tier("web", "https://example.com/blog", "Example") == "tertiary"
    assert classify_source_tier("manual", "", "shinkai") == "agent_inference"
    assert source_reliability_score("primary", extracted=True) > source_reliability_score(
        "tertiary"
    )


def test_source_tier_corporate_newsroom_is_primary() -> None:
    # Corporate newsroom subdomains — the SK Hynix-style case that surfaced
    # during the 2026-06-17 Vertex Grounding quality eval.
    skhynix_url = "https://news.skhynix.com/2026-market-outlook/"
    assert classify_source_tier("web", skhynix_url, "news.skhynix.com") == "primary"
    assert (
        classify_source_tier("web", "https://newsroom.intel.com/foo", "newsroom.intel.com")
        == "primary"
    )
    assert (
        classify_source_tier("web", "https://press.nvidia.com/release/x", "press.nvidia.com")
        == "primary"
    )
    onto_url = "https://ontoinnovation.com/news-releases/x"
    assert classify_source_tier("web", onto_url, "ontoinnovation.com") == "primary"
    assert (
        classify_source_tier("web", "https://camtek.com/investor-relations/", "camtek.com")
        == "primary"
    )


def test_source_tier_secondary_whitelist_extended() -> None:
    # Major financial press besides Reuters/Bloomberg/WSJ/FT.
    assert (
        classify_source_tier("web", "https://www.cnbc.com/2026/06/x", "cnbc.com") == "secondary"
    )
    assert (
        classify_source_tier("web", "https://asia.nikkei.com/x", "Nikkei Asia") == "secondary"
    )
    caixin_url = "https://www.caixinglobal.com/x"
    assert classify_source_tier("web", caixin_url, "Caixin Global") == "secondary"
    # Specialty industry trade press.
    assert (
        classify_source_tier(
            "web", "https://semianalysis.com/p/hbm-supply", "SemiAnalysis"
        )
        == "secondary"
    )
    assert (
        classify_source_tier("web", "https://www.digitimes.com/news/x", "Digitimes") == "secondary"
    )
    assert (
        classify_source_tier("web", "https://www.trendforce.com/press/x", "TrendForce")
        == "secondary"
    )


def test_source_tier_aggregator_short_circuit() -> None:
    # Yahoo Finance is an aggregator, not a primary newsroom, despite the
    # "news.yahoo.com" subdomain that would otherwise trip _PRIMARY_URL_HINTS.
    assert (
        classify_source_tier("web", "https://news.yahoo.com/some-story", "news.yahoo.com")
        == "tertiary"
    )
    assert (
        classify_source_tier("web", "https://finance.yahoo.com/quote/NVDA", "finance.yahoo.com")
        == "tertiary"
    )


def test_claim_assessment_requires_source_quality_and_tracks_stale_sources() -> None:
    now = 2_000_000_000.0
    primary = SourceRef(
        source_id="src_primary",
        type="filing",
        tier="primary",
        url="https://www.sec.gov/example",
        title="10-Q",
        publisher="SEC",
        published_at=now,
        primary_source_flag=True,
        reliability=0.94,
    )
    secondary = SourceRef(
        source_id="src_secondary",
        type="news",
        tier="secondary",
        url="https://www.reuters.com/example",
        title="Reuters story",
        publisher="Reuters",
        published_at=now,
        reliability=0.74,
    )
    stale = SourceRef(
        source_id="src_stale",
        type="research_report",
        tier="secondary",
        url="https://example.com/old",
        title="Old report",
        publisher="Example",
        published_at=now - 900 * 24 * 60 * 60,
        reliability=0.7,
    )
    refute = SourceRef(
        source_id="src_refute",
        type="ir",
        tier="primary",
        url="https://example.com/ir",
        title="Company IR",
        publisher="Company",
        published_at=now,
        primary_source_flag=True,
        reliability=0.9,
    )

    weak = assess_claim_support([secondary], now=now)
    supported = assess_claim_support([primary, secondary], now=now)
    stale_only = assess_claim_support([stale], now=now)
    refuted = assess_claim_support([primary, secondary], [refute], now=now)

    assert weak.status == "weak"
    assert weak.verification == "insufficient"
    assert supported.status == "supported"
    assert supported.verification == "support"
    assert supported.primary_source_count == 1
    assert stale_only.verification == "stale"
    assert stale_only.stale_source_ids == ["src_stale"]
    assert refuted.status == "contradicted"
    assert refuted.verification == "refute"
