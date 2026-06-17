from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha1
from urllib.parse import urlparse

from shinkai_api.agent.frontier import FrontierItem, FrontierQueue
from shinkai_api.agent.hypothesis import (
    apply_critic_penalty,
    apply_human_correction,
    promote_contradicting,
    promote_supporting,
)
from shinkai_api.agent.personas import aggregate_critiques, evaluate_dossier
from shinkai_api.core.config import settings
from shinkai_api.graph import Edge, GraphDelta, Node, default_graph_store, edge_id, node_id
from shinkai_api.llm import DeepSeekClient, DeepSeekError
from shinkai_api.research import (
    CandidateCompany,
    Claim,
    ClaimAssessment,
    CompanyDossier,
    Evidence,
    ResearchTask,
    SourceRef,
    assess_claim_support,
    classify_source_tier,
    default_research_store,
    source_reliability_score,
)
from shinkai_api.research.models import Hypothesis
from shinkai_api.runs.models import Run
from shinkai_api.runs.store import default_run_store
from shinkai_api.schemas.events import AgentEvent
from shinkai_api.tools import default_tool_registry
from shinkai_api.tools.base import ToolResult

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}\d?$")

# Soft source-quality steer appended to every Vertex Grounding query the
# harness emits. Vertex's google_search tool has no native domain filter, so
# this is the only knob we have to bias Gemini toward primary / trade press
# instead of SEO farms. Conservative wording (`prefer`, not `only`) keeps
# the search broad enough to still surface contradicting / off-narrative
# results — the value-investing checklist needs both.
_SOURCE_QUALITY_HINT = (
    "(prefer SEC filings, company investor relations / press releases, "
    "Bloomberg, Reuters, WSJ, Financial Times, SemiAnalysis, "
    "SemiEngineering, Digitimes, TrendForce; avoid SEO rewrites)"
)


@dataclass(frozen=True)
class SupplyChainLayer:
    name: str
    seed_giants: list[str]
    bottleneck: str
    evidence_stub: str
    companies: list[dict[str, object]]
    next_frontier: str


@dataclass(frozen=True)
class LayerEvidence:
    node: Node
    source_backed: bool
    sources: list[SourceRef]
    evidence_records: list[Evidence]
    contradicting_sources: list[SourceRef]
    contradicting_evidence_records: list[Evidence]
    tool_result: ToolResult | None
    extract_result: ToolResult | None = None


AI_SUPPLY_CHAIN_LAYERS: list[SupplyChainLayer] = [
    SupplyChainLayer(
        name="Power and electrical infrastructure",
        seed_giants=["NVIDIA", "Microsoft", "Amazon", "Google", "Meta"],
        bottleneck=(
            "AI data center growth is increasingly constrained by grid interconnects, "
            "switchgear, UPS capacity, backup generation, and power density."
        ),
        evidence_stub=(
            "Public AI data center buildouts repeatedly cite power availability "
            "and energization timelines as gating constraints."
        ),
        companies=[
            {"ticker": "VRT", "name": "Vertiv", "quality": 0.76, "underwater": 0.42},
            {"ticker": "POWL", "name": "Powell Industries", "quality": 0.71, "underwater": 0.66},
            {"ticker": "NVT", "name": "nVent Electric", "quality": 0.69, "underwater": 0.48},
        ],
        next_frontier=(
            "Trace sub-suppliers for switchgear, busway, thermal power management, "
            "and grid interconnect equipment."
        ),
    ),
    SupplyChainLayer(
        name="Advanced packaging, HBM, and test capacity",
        seed_giants=["TSMC", "NVIDIA", "Broadcom", "AMD"],
        bottleneck=(
            "AI accelerator availability depends on CoWoS-like advanced packaging, HBM "
            "integration, probe cards, handlers, inspection, and metrology."
        ),
        evidence_stub=(
            "HBM and advanced packaging capacity are cited as constraints on "
            "accelerator ramp schedules."
        ),
        companies=[
            {"ticker": "FORM", "name": "FormFactor", "quality": 0.72, "underwater": 0.61},
            {"ticker": "ONTO", "name": "Onto Innovation", "quality": 0.75, "underwater": 0.55},
            {"ticker": "COHU", "name": "Cohu", "quality": 0.63, "underwater": 0.7},
        ],
        next_frontier=(
            "Separate durable test/metrology exposure from cyclical semiconductor "
            "equipment recovery."
        ),
    ),
    SupplyChainLayer(
        name="Cluster networking and optical interconnect",
        seed_giants=["NVIDIA", "Broadcom", "Meta", "Microsoft"],
        bottleneck=(
            "Large training and inference clusters create non-linear east-west traffic, "
            "raising demand for optical modules, DSPs, high-speed cables, and switching."
        ),
        evidence_stub=(
            "AI clusters require high-bandwidth, low-latency interconnect across "
            "accelerators and racks."
        ),
        companies=[
            {"ticker": "CRDO", "name": "Credo Technology", "quality": 0.61, "underwater": 0.58},
            {"ticker": "COHR", "name": "Coherent", "quality": 0.58, "underwater": 0.52},
            {"ticker": "LITE", "name": "Lumentum", "quality": 0.54, "underwater": 0.57},
        ],
        next_frontier=(
            "Validate whether optical AI exposure is structurally profitable or "
            "only a cyclical inventory rebound."
        ),
    ),
    SupplyChainLayer(
        name="Thermal systems and liquid cooling",
        seed_giants=["NVIDIA", "Microsoft", "Meta", "Amazon"],
        bottleneck=(
            "Rack power density pushes air cooling limits, forcing liquid cooling, CDUs, "
            "heat exchangers, facility redesign, and maintenance capability."
        ),
        evidence_stub=(
            "Next-generation AI server racks are moving toward higher thermal "
            "density and liquid cooling adoption."
        ),
        companies=[
            {"ticker": "MOD", "name": "Modine", "quality": 0.67, "underwater": 0.64},
            {
                "ticker": "WTS",
                "name": "Watts Water Technologies",
                "quality": 0.73,
                "underwater": 0.45,
            },
            {"ticker": "VRT", "name": "Vertiv", "quality": 0.76, "underwater": 0.42},
        ],
        next_frontier="Map component suppliers below CDUs and facility thermal integrators.",
    ),
]


class ShinkaiHarness:
    """Long-running harness boundary for shinkai.

    The model proposes local judgments, but the harness owns the loop:
    frontier selection, graph writes, event emission, review, optimization,
    and budget termination. Spiral 1 uses deterministic synthetic evidence so
    the observability and data contracts are testable before real LLM/search IO.
    """

    async def run(self, run: Run) -> AsyncIterator[AgentEvent]:
        discovery_mode = str(run.scope.get("discovery_mode") or "auto")
        prefer_llm = discovery_mode == "llm_driven" or (
            discovery_mode == "auto" and bool(settings.deepseek_api_key)
        )
        force_llm = discovery_mode == "llm_driven" or bool(
            run.scope.get("force_llm_planner")
        )
        planned_layers: list[SupplyChainLayer] = []
        planner_payload: dict | None = None
        planner_source = "deterministic_fallback"
        raw_frontier_count = 0
        validated_layer_count = 0
        reject_reason: str | None = None

        if prefer_llm and settings.deepseek_api_key:
            yield AgentEvent(
                type="tool_call",
                run_id=run.id,
                data={
                    "name": "deepseek_frontier_planner",
                    "args": {"model": settings.llm_model, "theme": run.anchor},
                    "autonomous": True,
                },
            )
            try:
                planner_payload = await self._plan_with_deepseek(run)
                frontiers = planner_payload.get("frontiers", [])
                raw_frontier_count = len(frontiers) if isinstance(frontiers, list) else 0
                llm_layers, reject_reason = self._validate_planner_payload(planner_payload)
                validated_layer_count = len(llm_layers)
                if llm_layers:
                    planned_layers = llm_layers
                    planner_source = "deepseek_llm_planner"
                usage = planner_payload.get("_usage", {})
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "deepseek_frontier_planner",
                        "ok": bool(llm_layers),
                        "summary": (
                            "DeepSeek proposed frontiers."
                            if llm_layers
                            else f"DeepSeek output rejected: {reject_reason}"
                        ),
                        "preview": {
                            "raw_frontier_count": raw_frontier_count,
                            "validated_layer_count": validated_layer_count,
                            "usage": usage,
                            "source_used": planner_source,
                            "reject_reason": reject_reason,
                        },
                    },
                )
                yield AgentEvent(
                    type="usage",
                    run_id=run.id,
                    data={
                        "input_tokens": int(usage.get("input_tokens") or 0),
                        "output_tokens": int(usage.get("output_tokens") or 0),
                        "provider": "deepseek",
                        "model": settings.llm_model,
                    },
                )
            except DeepSeekError as exc:
                reject_reason = f"deepseek_error: {exc}"
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "deepseek_frontier_planner",
                        "ok": False,
                        "error": str(exc),
                        "fallback": (
                            "deterministic_supply_chain_layers" if not force_llm else "fail"
                        ),
                    },
                )

        if not planned_layers:
            if force_llm:
                yield AgentEvent(
                    type="planner_proposals",
                    run_id=run.id,
                    data={
                        "source": "force_llm_fail",
                        "raw_frontier_count": raw_frontier_count,
                        "validated_layer_count": 0,
                        "sample_layers": [],
                        "reject_reason": reject_reason or "no_api_key",
                        "discovery_mode": discovery_mode,
                        "force_llm_planner": True,
                    },
                )
                raise RuntimeError(
                    "force_llm_planner is set but planner did not produce valid layers: "
                    f"{reject_reason or 'no API key'}"
                )
            planned_layers = list(AI_SUPPLY_CHAIN_LAYERS)
            planner_source = (
                "fallback_after_reject" if reject_reason else "deterministic_fallback"
            )

        yield AgentEvent(
            type="planner_proposals",
            run_id=run.id,
            data={
                "source": planner_source,
                "raw_frontier_count": raw_frontier_count,
                "validated_layer_count": validated_layer_count,
                "sample_layers": [layer.name for layer in planned_layers[:3]],
                "reject_reason": reject_reason,
                "discovery_mode": discovery_mode,
                "force_llm_planner": force_llm,
            },
        )

        yield AgentEvent(
            type="role_step_completed",
            run_id=run.id,
            data={
                "role": "planner",
                "step": "planner_source_selected",
                "planner_source": planner_source,
                "frontier_count": len(planned_layers),
                "discovery_mode": discovery_mode,
            },
        )

        frontier_items = _frontier_items_from_layers(planned_layers)
        frontier_queue = FrontierQueue(frontier_items)
        layer_by_frontier_id = {
            item.frontier_id: layer
            for item, layer in zip(frontier_items, planned_layers, strict=True)
        }
        max_loops = min(
            len(frontier_items),
            max(1, run.budget.max_tool_calls // max(1, settings.harness_max_loops_divisor)),
        )
        objective = run.scope.get(
            "objective",
            "autonomously discover AI supply-chain bottlenecks and under-covered companies",
        )

        yield AgentEvent(
            type="plan",
            run_id=run.id,
            data={
                "objective": objective,
                "review_optimize_loop": [
                    "plan_frontier",
                    "expand_layer",
                    "create_claims",
                    "surface_candidates",
                    "score_candidates",
                    "review_trace",
                    "optimize_frontier",
                ],
                "termination": "stop when objective is met or budget is exhausted",
                "planner": "deepseek" if planner_payload else "deterministic",
                "roles": {
                    "planner": "build and score frontier queue",
                    "researcher": "execute source search and graph/research writes",
                    "reviewer": "validate claims against support/refute/stale evidence",
                    "optimizer": "reprioritize the frontier queue after review",
                },
                "frontier_queue": frontier_queue.snapshot(),
            },
        )
        yield AgentEvent(
            type="role_step_completed",
            run_id=run.id,
            data={
                "role": "planner",
                "step": "frontier_queue_initialized",
                "frontier_count": len(frontier_items),
                "queue": frontier_queue.snapshot(),
            },
        )

        live_sources = bool(run.scope.get("allow_live_sources", False))
        checkpoints_enabled = bool(run.scope.get("checkpoints_enabled", False))
        critics_enabled = bool(run.scope.get("critics_enabled", False))
        checkpoint_raised_already = False
        consumed_injection_ids = await self._seed_consumed_injection_ids(run.id)
        filter_policy_patches: list[str] = list(run.scope.get("filter_policy_patches", []))
        current_layer_name: list[str | None] = [None]

        for loop_index in range(1, max_loops + 1):
            async for ack_event in self._consume_pending_injections(
                run,
                consumed_injection_ids,
                frontier_queue=frontier_queue,
                filter_policy_patches=filter_policy_patches,
                current_layer_name=current_layer_name,
            ):
                yield ack_event
            frontier_item = frontier_queue.pop_next(
                source_filter={"deterministic_planner", "planner"}
            )
            if frontier_item is None:
                break
            layer = layer_by_frontier_id[frontier_item.frontier_id]
            current_layer_name[0] = layer.name
            yield AgentEvent(
                type="frontier_selected",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "frontier_id": frontier_item.frontier_id,
                    "frontier": frontier_item.name,
                    "selection_score": frontier_item.selection_score,
                    "priority": frontier_item.priority,
                    "confidence": frontier_item.confidence,
                    "expected_value": frontier_item.expected_value,
                    "estimated_cost": frontier_item.estimated_cost,
                    "reason": frontier_item.reason,
                    "queue_remaining": frontier_queue.queued_count,
                    "selected_by": "planner",
                },
            )
            yield AgentEvent(
                type="supply_chain_layer_started",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "layer": layer.name,
                    "seed_giants": layer.seed_giants,
                    "autonomous": True,
                },
            )

            if live_sources:
                search_query = self._evidence_query(layer)
                yield AgentEvent(
                    type="tool_call",
                    run_id=run.id,
                    data={
                        "name": "web_search",
                        "args": {"query": search_query, "max_results": 3},
                        "loop_index": loop_index,
                        "layer": layer.name,
                        "autonomous": True,
                    },
                )
                search_result = await self._run_web_search(search_query)
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "web_search",
                        "ok": search_result.ok,
                        "summary": search_result.summary,
                        "preview": search_result.data,
                        "loop_index": loop_index,
                        "layer": layer.name,
                    },
                )
                extract_result: ToolResult | None = None
                first_url = _first_result_url(search_result)
                if first_url:
                    yield AgentEvent(
                        type="tool_call",
                        run_id=run.id,
                        data={
                            "name": "web_extract",
                            "args": {"url": first_url},
                            "loop_index": loop_index,
                            "layer": layer.name,
                            "autonomous": True,
                        },
                    )
                    extract_result = await self._run_web_extract(first_url)
                    yield AgentEvent(
                        type="tool_result",
                        run_id=run.id,
                        data={
                            "name": "web_extract",
                            "ok": extract_result.ok,
                            "summary": extract_result.summary,
                            "preview": {
                                "url": extract_result.data.get("url"),
                                "title": extract_result.data.get("title"),
                                "excerpt": str(extract_result.data.get("excerpt") or "")[:300],
                            },
                            "loop_index": loop_index,
                            "layer": layer.name,
                        },
                    )
                contradiction_query = self._contradiction_query(layer)
                yield AgentEvent(
                    type="tool_call",
                    run_id=run.id,
                    data={
                        "name": "web_search",
                        "args": {"query": contradiction_query, "max_results": 3},
                        "loop_index": loop_index,
                        "layer": layer.name,
                        "purpose": "refute_claim",
                        "autonomous": True,
                    },
                )
                contradiction_search_result = await self._run_web_search(contradiction_query)
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "web_search",
                        "ok": contradiction_search_result.ok,
                        "summary": contradiction_search_result.summary,
                        "preview": contradiction_search_result.data,
                        "loop_index": loop_index,
                        "layer": layer.name,
                        "purpose": "refute_claim",
                    },
                )
                evidence = self._evidence_from_tool_results(
                    layer,
                    run.id,
                    search_query,
                    search_result,
                    extract_result,
                    contradiction_query,
                    contradiction_search_result,
                )
            else:
                evidence = self._stub_evidence(layer, run.id)

            evidence_ids = [record.evidence_id for record in evidence.evidence_records]
            contradicting_evidence_ids = [
                record.evidence_id for record in evidence.contradicting_evidence_records
            ]
            assessment = assess_claim_support(
                evidence.sources if evidence.source_backed else [],
                evidence.contradicting_sources,
            )
            claim_status = assessment.status
            claim_verification = assessment.verification
            independent_source_count = assessment.independent_source_count

            frontier_node = Node(
                id=node_id("frontier", layer.name),
                type="Entity",
                label=layer.name,
                confidence=0.78,
                data={"kind": "SupplyChainLayer", "seed_giants": layer.seed_giants},
                tags=["ai-supply-chain", "frontier"],
            )
            bottleneck_node = Node(
                id=node_id("claim", layer.bottleneck),
                type="Claim",
                label=f"Bottleneck: {layer.name}",
                confidence=0.68,
                source_refs=evidence_ids,
                data={
                    "statement": layer.bottleneck,
                    "claim_kind": "Qualitative",
                    "status": claim_status,
                    "verification": claim_verification,
                    "independent_source_count": independent_source_count,
                    "primary_source_count": assessment.primary_source_count,
                    "contradicting_source_count": assessment.contradicting_source_count,
                    "stale_source_ids": assessment.stale_source_ids,
                    "evidence_ids": evidence_ids,
                    "contradicting_evidence_ids": contradicting_evidence_ids,
                    "rationale": assessment.rationale,
                },
                tags=["bottleneck", "ai-infrastructure", f"claim-{claim_status}"],
            )
            bottleneck_claim = Claim(
                claim_id=bottleneck_node.id,
                run_id=run.id,
                text=layer.bottleneck,
                topic=layer.name,
                status=claim_status,
                verification=claim_verification,
                confidence=bottleneck_node.confidence,
                supporting_evidence_ids=evidence_ids,
                evidence_ids=evidence_ids,
                contradicting_evidence_ids=contradicting_evidence_ids,
                stale_evidence_ids=_stale_evidence_ids(evidence, assessment.stale_source_ids),
                hypothesis_id=_stable_id("hyp", run.id, layer.name),
                metadata={
                    "kind": "bottleneck",
                    "independent_source_count": independent_source_count,
                    "primary_source_count": assessment.primary_source_count,
                    "contradicting_source_count": assessment.contradicting_source_count,
                    "stale_source_ids": assessment.stale_source_ids,
                    "rationale": assessment.rationale,
                    "source_backed": evidence.source_backed,
                },
            )
            evidence_node = evidence.node
            base_edges = [
                Edge(
                    id=edge_id(frontier_node.id, "decomposes_into", bottleneck_node.id),
                    type="logical",
                    relation="decomposes_into",
                    from_node=frontier_node.id,
                    to_node=bottleneck_node.id,
                    confidence=0.7,
                ),
                Edge(
                    id=edge_id(evidence_node.id, "supports", bottleneck_node.id),
                    type="evidential",
                    relation="supports",
                    from_node=evidence_node.id,
                    to_node=bottleneck_node.id,
                    confidence=0.72 if evidence.source_backed else 0.5,
                    source_refs=evidence_ids,
                ),
            ]

            candidate_nodes: list[Node] = []
            candidate_edges: list[Edge] = []
            candidate_detail_nodes: list[Node] = []
            candidate_detail_edges: list[Edge] = []
            claim_records = [bottleneck_claim]
            candidate_records: list[CandidateCompany] = []
            dossier_records: list[CompanyDossier] = []
            task_records: list[ResearchTask] = []
            rejected_by_validator: list[str] = []
            for company in layer.companies:
                ticker = str(company["ticker"])
                per_company_evidence_ids = list(evidence_ids)
                # Real network calls (validator → yfinance/SEC, sec_filings
                # → SEC EDGAR) are only made when the run opted into live
                # sources. Tests run with ``allow_live_sources=False`` and
                # keep the deterministic candidate set intact.
                if live_sources:
                    validation = await self._validate_ticker_safely(ticker)
                    if validation and not validation.get(
                        "industry_eligible", True
                    ):
                        rejected_by_validator.append(ticker)
                        yield AgentEvent(
                            type="candidate_rejected_by_validator",
                            run_id=run.id,
                            data={
                                "loop_index": loop_index,
                                "ticker": ticker,
                                "name": validation.get("name")
                                or str(company["name"]),
                                "proposed_layer": layer.name,
                                "actual_sector": validation.get("sector") or "",
                                "actual_industry": validation.get("industry") or "",
                                "reject_reason": validation.get("reject_reason")
                                or "ineligible_industry",
                                "found_via": validation.get("found_via") or "",
                            },
                        )
                        continue

                    sec_records = await self._sec_filings_evidence(
                        ticker, run.id, layer.name
                    )
                    if sec_records:
                        new_sources, new_evidence = sec_records
                        evidence.sources.extend(new_sources)
                        evidence.evidence_records.extend(new_evidence)
                        per_company_evidence_ids.extend(
                            record.evidence_id for record in new_evidence
                        )

                quality = float(company["quality"])
                underwater = float(company["underwater"])
                score = round((quality * 0.55) + (underwater * 0.45), 3)
                q1_pass = quality >= 0.65
                q2_pass = underwater >= 0.55
                decision = "queue_mode_a" if q1_pass and q2_pass and score >= 0.62 else "watch_only"
                candidate_status = "qualified" if decision == "queue_mode_a" else "watchlist"
                risk_flags = _candidate_risk_flags(q1_pass, q2_pass, evidence.source_backed)
                next_questions = _candidate_questions(str(company["name"]), layer.name)
                company_node = Node(
                    id=node_id("company", str(company["ticker"])),
                    type="Entity",
                    label=f"{company['name']} ({company['ticker']})",
                    confidence=score,
                    data={
                        "kind": "Company",
                        "ticker": company["ticker"],
                        "name": company["name"],
                        "quality_score": quality,
                        "underwater_score": underwater,
                        "combined_score": score,
                        "candidate_status": candidate_status,
                        "risk_flags": risk_flags,
                    },
                    tags=["candidate", "mode-b"],
                )
                claim_node = Node(
                    id=node_id("claim", f"{company['ticker']} {layer.name} exposure"),
                    type="Claim",
                    label=f"{company['ticker']} bottleneck exposure",
                    confidence=score,
                    source_refs=evidence_ids,
                    data={
                        "statement": (
                            f"{company['name']} may be a second-order beneficiary of "
                            f"{layer.name} AI infrastructure constraints."
                        ),
                        "claim_kind": "Forward",
                        "ticker": company["ticker"],
                        "status": claim_status,
                        "verification": claim_verification,
                        "evidence_ids": evidence_ids,
                        "contradicting_evidence_ids": contradicting_evidence_ids,
                        "independent_source_count": independent_source_count,
                        "primary_source_count": assessment.primary_source_count,
                        "rationale": assessment.rationale,
                    },
                    tags=["candidate-claim", "underwriting-input", f"claim-{claim_status}"],
                )
                claim_records.append(
                    Claim(
                        claim_id=claim_node.id,
                        run_id=run.id,
                        topic=layer.name,
                        text=str(claim_node.data["statement"]),
                        status=claim_status,
                        verification=claim_verification,
                        confidence=score,
                        supporting_evidence_ids=per_company_evidence_ids,
                        evidence_ids=per_company_evidence_ids,
                        contradicting_evidence_ids=contradicting_evidence_ids,
                        stale_evidence_ids=_stale_evidence_ids(
                            evidence,
                            assessment.stale_source_ids,
                        ),
                        hypothesis_id=_stable_id("hyp", run.id, layer.name),
                        metadata={
                            "kind": "candidate_exposure",
                            "ticker": company["ticker"],
                            "independent_source_count": independent_source_count,
                            "primary_source_count": assessment.primary_source_count,
                            "rationale": assessment.rationale,
                            "source_backed": evidence.source_backed,
                        },
                    )
                )
                question_node = Node(
                    id=node_id("question", f"{company['ticker']} underwriting question"),
                    type="Question",
                    label=f"{company['ticker']} underwriting question",
                    confidence=0.62,
                    data={
                        "question_text": (
                            f"Is {company['name']}'s AI exposure direct, durable, "
                            "and margin-accretive enough for Mode A underwriting?"
                        ),
                        "priority": "high" if decision == "queue_mode_a" else "medium",
                        "status": "open",
                        "ticker": company["ticker"],
                        "next_questions": next_questions,
                    },
                    tags=["open-question", "mode-a-input"],
                )
                candidate_record = CandidateCompany(
                    candidate_id=company_node.id,
                    run_id=run.id,
                    ticker=str(company["ticker"]),
                    name=str(company["name"]),
                    supply_chain_layer=layer.name,
                    thesis=str(claim_node.data["statement"]),
                    status=candidate_status,
                    quality_score=quality,
                    under_coverage_score=underwater,
                    relevance_score=score,
                    claim_ids=[bottleneck_node.id, claim_node.id],
                    evidence_ids=evidence_ids,
                    risk_flags=risk_flags,
                    next_questions=next_questions,
                    metadata={
                        "decision": decision,
                        "q1_quality_pass": q1_pass,
                        "q2_underwater_pass": q2_pass,
                        "source_backed": evidence.source_backed,
                    },
                )
                candidate_records.append(candidate_record)
                dossier_record = _build_company_dossier(
                    run_id=run.id,
                    layer=layer,
                    candidate=candidate_record,
                    score=score,
                    q1_pass=q1_pass,
                    q2_pass=q2_pass,
                    assessment=assessment,
                )
                dossier_records.append(dossier_record)
                task_records.append(
                    ResearchTask(
                        task_id=_stable_id("task", run.id, str(company["ticker"]), layer.name),
                        run_id=run.id,
                        title=f"Deep research: {company['ticker']} in {layer.name}",
                        objective=(
                            f"Validate {company['name']}'s direct, durable, and "
                            f"margin-accretive exposure to {layer.name}."
                        ),
                        status="completed",
                        assigned_agent="shinkai:company-subagent",
                        claim_ids=[claim_node.id],
                        candidate_ids=[company_node.id],
                        evidence_ids=evidence_ids,
                        metadata={
                            "ticker": company["ticker"],
                            "decision": decision,
                            "risk_flags": risk_flags,
                            "next_questions": next_questions,
                        },
                    )
                )
                candidate_nodes.append(company_node)
                candidate_detail_nodes.extend([claim_node, question_node])
                candidate_edges.append(
                    Edge(
                        id=edge_id(company_node.id, "participates_in", frontier_node.id),
                        type="structural",
                        relation="participates_in",
                        from_node=company_node.id,
                        to_node=frontier_node.id,
                        confidence=0.64,
                    )
                )
                candidate_detail_edges.extend(
                    [
                        Edge(
                            id=edge_id(company_node.id, "depends_on", claim_node.id),
                            type="logical",
                            relation="depends_on",
                            from_node=company_node.id,
                            to_node=claim_node.id,
                            confidence=score,
                            source_refs=evidence_ids,
                        ),
                        Edge(
                            id=edge_id(evidence_node.id, "supports", claim_node.id),
                            type="evidential",
                            relation="supports",
                            from_node=evidence_node.id,
                            to_node=claim_node.id,
                            confidence=0.68 if evidence.source_backed else 0.48,
                            source_refs=evidence_ids,
                        ),
                        Edge(
                            id=edge_id(question_node.id, "depends_on", company_node.id),
                            type="logical",
                            relation="depends_on",
                            from_node=question_node.id,
                            to_node=company_node.id,
                            confidence=0.62,
                        ),
                    ]
                )
                if decision == "queue_mode_a":
                    thesis_node = Node(
                        id=node_id("thesis", f"{company['ticker']} initial thesis"),
                        type="Thesis",
                        label=f"{company['ticker']} initial underwriting thesis",
                        confidence=score,
                        source_refs=evidence_ids,
                        data={
                            "statement": (
                                f"{company['name']} should enter Mode A underwriting "
                                f"for {layer.name} exposure."
                            ),
                            "position": "watchlist",
                            "time_horizon": "medium",
                            "ticker": company["ticker"],
                            "kill_criteria": [
                                "AI-linked revenue exposure is indirect or immaterial",
                                "Cycle-normalized margins do not support quality score",
                                "Market attention is already consensus-level",
                            ],
                        },
                        tags=["initial-thesis", "mode-a-queue"],
                    )
                    candidate_detail_nodes.append(thesis_node)
                    candidate_detail_edges.append(
                        Edge(
                            id=edge_id(thesis_node.id, "depends_on", claim_node.id),
                            type="logical",
                            relation="depends_on",
                            from_node=thesis_node.id,
                            to_node=claim_node.id,
                            confidence=score,
                            source_refs=evidence_ids,
                        )
                    )

            task_records.append(
                ResearchTask(
                    task_id=_stable_id("task", run.id, "theme", layer.name),
                    run_id=run.id,
                    title=f"Theme deep research: {layer.name}",
                    objective=(
                        f"Trace {layer.name} from AI mega-cap demand into bottlenecks, "
                        "evidence, and candidate companies."
                    ),
                    status="completed",
                    assigned_agent="shinkai:theme-agent",
                    claim_ids=[claim.claim_id for claim in claim_records],
                    candidate_ids=[candidate.candidate_id for candidate in candidate_records],
                    evidence_ids=evidence_ids,
                    metadata={
                        "loop_index": loop_index,
                        "seed_giants": layer.seed_giants,
                        "next_frontier": layer.next_frontier,
                    },
                )
            )
            for record in evidence.evidence_records:
                record.supports_claim_ids = [claim.claim_id for claim in claim_records]
            await self._persist_research_records(
                evidence=evidence,
                claims=claim_records,
                candidates=candidate_records,
                dossiers=dossier_records,
                tasks=task_records,
            )
            candidate_records_by_ticker = {
                candidate.ticker: candidate for candidate in candidate_records
            }
            candidate_tasks_by_ticker = {
                str(task.metadata.get("ticker")): task
                for task in task_records
                if task.metadata.get("ticker")
            }
            candidate_dossiers_by_ticker = {
                dossier.ticker: dossier for dossier in dossier_records
            }
            candidate_scores_by_ticker = {
                candidate.ticker: {
                    "quality": candidate.quality_score,
                    "underwater": candidate.under_coverage_score,
                    "score": candidate.relevance_score,
                    "q1_pass": candidate.quality_score >= 0.65,
                    "q2_pass": candidate.under_coverage_score >= 0.55,
                    "decision": str(candidate.metadata.get("decision") or "watch_only"),
                }
                for candidate in candidate_records
            }

            delta = GraphDelta(
                nodes=[
                    frontier_node,
                    bottleneck_node,
                    evidence_node,
                    *candidate_nodes,
                    *candidate_detail_nodes,
                ],
                edges=[*base_edges, *candidate_edges, *candidate_detail_edges],
                summary=f"Expanded {layer.name} and surfaced {len(candidate_nodes)} candidates.",
            )
            await default_graph_store.apply_delta(run.id, delta)

            yield AgentEvent(
                type="frontier_expanded",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "layer": layer.name,
                    "bottleneck": layer.bottleneck,
                    "seed_giants": layer.seed_giants,
                    "next_frontier": layer.next_frontier,
                },
            )
            yield AgentEvent(
                type="theme_discovered",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "theme": layer.name,
                    "confidence": 0.78,
                    "why": layer.bottleneck,
                    "source": "autonomous_supply_chain_expansion",
                },
            )
            yield AgentEvent(
                type="evidence_found",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "layer": layer.name,
                    "evidence_id": evidence_node.id,
                    "summary": evidence_node.data.get("excerpt", layer.evidence_stub),
                    "source_uri": evidence_node.data.get("source_uri"),
                    "source_title": evidence_node.data.get("source_title"),
                    "source_tiers": [source.tier for source in evidence.sources],
                    "primary_source_count": assessment.primary_source_count,
                    "citation_urls": [record.citation_url for record in evidence.evidence_records],
                    "quotes": [record.quote for record in evidence.evidence_records[:2]],
                    "source_backed": evidence.source_backed,
                    "needs_real_source": not evidence.source_backed,
                },
            )
            yield AgentEvent(
                type="claim_created",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "claim_id": bottleneck_node.id,
                    "claim": layer.bottleneck,
                    "confidence": bottleneck_node.confidence,
                },
            )
            yield AgentEvent(
                type="claim_validated",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "claim_id": bottleneck_node.id,
                    "status": claim_status,
                    "verification": claim_verification,
                    "independent_source_count": independent_source_count,
                    "required_independent_sources": bottleneck_claim.required_independent_sources,
                    "primary_source_count": assessment.primary_source_count,
                    "evidence_ids": evidence_ids,
                    "contradicting_evidence_ids": contradicting_evidence_ids,
                    "contradicting_source_count": assessment.contradicting_source_count,
                    "stale_source_ids": assessment.stale_source_ids,
                    "rationale": assessment.rationale,
                    "source_backed": evidence.source_backed,
                },
            )
            hypothesis_id = _stable_id("hyp", run.id, layer.name)
            hypothesis_claim = (
                f"{layer.name} is a candidate AI infrastructure bottleneck "
                "where second-order suppliers may be more under-covered than seed giants."
            )
            falsification_condition = (
                f"Two independent primary sources refute the claim that {layer.name} "
                "is structurally constrained, OR the layer's next frontier "
                f"({layer.next_frontier}) yields no supplier improvement signal."
            )
            hypothesis = Hypothesis(
                hypothesis_id=hypothesis_id,
                run_id=run.id,
                layer=layer.name,
                claim=hypothesis_claim,
                confidence=0.5,
                falsification_condition=falsification_condition,
            )
            await default_research_store.upsert_hypothesis(hypothesis)
            yield AgentEvent(
                type="hypothesis_created",
                run_id=run.id,
                data={
                    "hypothesis_id": hypothesis_id,
                    "layer": layer.name,
                    "claim": hypothesis_claim,
                    "initial_confidence": 0.5,
                    "falsification_condition": falsification_condition,
                },
            )
            yield AgentEvent(
                type="judgment_created",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "hypothesis_id": hypothesis_id,
                    "layer": layer.name,
                    "judgment": hypothesis_claim,
                    "confidence": 0.66,
                    "support": [layer.bottleneck],
                },
            )
            sources_by_id = {source.source_id: source for source in evidence.sources}
            sources_by_id.update(
                {source.source_id: source for source in evidence.contradicting_sources}
            )
            for evidence_record in evidence.evidence_records:
                source = sources_by_id.get(evidence_record.source_id)
                reliability = float(source.reliability) if source else 0.5
                point = promote_supporting(
                    hypothesis,
                    evidence_id=evidence_record.evidence_id,
                    reliability_score=reliability,
                )
                yield AgentEvent(
                    type="hypothesis_confidence_updated",
                    run_id=run.id,
                    data={
                        "hypothesis_id": hypothesis_id,
                        "prev_confidence": round(point.confidence - point.delta, 4),
                        "new_confidence": point.confidence,
                        "delta": point.delta,
                        "evidence_id": point.evidence_id,
                        "kind": point.kind,
                        "method": point.method,
                    },
                )
            for evidence_record in evidence.contradicting_evidence_records:
                source = sources_by_id.get(evidence_record.source_id)
                reliability = float(source.reliability) if source else 0.5
                point = promote_contradicting(
                    hypothesis,
                    evidence_id=evidence_record.evidence_id,
                    reliability_score=reliability,
                )
                yield AgentEvent(
                    type="hypothesis_confidence_updated",
                    run_id=run.id,
                    data={
                        "hypothesis_id": hypothesis_id,
                        "prev_confidence": round(point.confidence - point.delta, 4),
                        "new_confidence": point.confidence,
                        "delta": point.delta,
                        "evidence_id": point.evidence_id,
                        "kind": point.kind,
                        "method": point.method,
                    },
                )
            await default_research_store.upsert_hypothesis(hypothesis)

            for company in layer.companies:
                ticker = str(company["ticker"])
                cached = candidate_scores_by_ticker.get(ticker, {})
                quality = float(cached.get("quality") or company["quality"])
                underwater = float(cached.get("underwater") or company["underwater"])
                score = float(
                    cached.get("score") or round((quality * 0.55) + (underwater * 0.45), 3)
                )
                q1_pass = bool(cached.get("q1_pass", quality >= 0.65))
                q2_pass = bool(cached.get("q2_pass", underwater >= 0.55))
                decision = str(
                    cached.get("decision")
                    or ("queue_mode_a" if q1_pass and q2_pass and score >= 0.62 else "watch_only")
                )
                yield AgentEvent(
                    type="candidate_created",
                    run_id=run.id,
                    data={
                        "loop_index": loop_index,
                        "ticker": company["ticker"],
                        "name": company["name"],
                        "layer": layer.name,
                        "reason": (
                            "Potential second-order beneficiary tied to a concrete "
                            "AI bottleneck."
                        ),
                        "next_action": "Run Q1 quality and Q2 underwater filters.",
                    },
                )
                yield AgentEvent(
                    type="candidate_scored",
                    run_id=run.id,
                    data={
                        "loop_index": loop_index,
                        "ticker": company["ticker"],
                        "quality_score": quality,
                        "underwater_score": underwater,
                        "q1_quality_pass": q1_pass,
                        "q2_underwater_pass": q2_pass,
                        "combined_score": score,
                        "decision": decision,
                        "mode_a_ready": decision == "queue_mode_a",
                    },
                )
                candidate_record = candidate_records_by_ticker.get(str(company["ticker"]))
                task_record = candidate_tasks_by_ticker.get(str(company["ticker"]))
                dossier_record = candidate_dossiers_by_ticker.get(str(company["ticker"]))
                if candidate_record and task_record:
                    yield AgentEvent(
                        type="company_deep_analysis_completed",
                        run_id=run.id,
                        data={
                            "loop_index": loop_index,
                            "ticker": candidate_record.ticker,
                            "name": candidate_record.name,
                            "layer": candidate_record.supply_chain_layer,
                            "candidate_id": candidate_record.candidate_id,
                            "task_id": task_record.task_id,
                            "assigned_agent": task_record.assigned_agent,
                            "claim_ids": candidate_record.claim_ids,
                            "evidence_ids": candidate_record.evidence_ids,
                            "status": candidate_record.status,
                            "risk_flags": candidate_record.risk_flags,
                            "next_questions": candidate_record.next_questions,
                            "decision": candidate_record.metadata.get("decision"),
                        },
                    )
                if dossier_record:
                    if checkpoints_enabled and not checkpoint_raised_already:
                        yield AgentEvent(
                            type="checkpoint_raised",
                            run_id=run.id,
                            data={
                                "reason": "first_dossier_publication",
                                "loop_index": loop_index,
                                "ticker": dossier_record.ticker,
                                "decision": dossier_record.decision,
                                "prompt": (
                                    "First company dossier ready. Review the decision "
                                    "before subsequent dossiers are published."
                                ),
                            },
                        )
                        await default_run_store.set_status(
                            run.id,
                            "awaiting_checkpoint",
                            "awaiting_checkpoint",
                        )
                        checkpoint_raised_already = True
                    yield AgentEvent(
                        type="company_dossier_created",
                        run_id=run.id,
                        data={
                            "loop_index": loop_index,
                            "ticker": dossier_record.ticker,
                            "name": dossier_record.company_name,
                            "dossier_id": dossier_record.dossier_id,
                            "candidate_id": dossier_record.candidate_id,
                            "layer": dossier_record.supply_chain_layer,
                            "decision": dossier_record.decision,
                            "decision_rationale": dossier_record.decision_rationale,
                            "mode_a_checks": dossier_record.mode_a_checks,
                            "risk_factors": dossier_record.risk_factors,
                            "catalysts": dossier_record.catalysts,
                        },
                    )
                    if critics_enabled:
                        critic_input = {
                            "ticker": dossier_record.ticker,
                            "quality_score": quality,
                            "underwater_score": underwater,
                        }
                        primary_source_count = sum(
                            1 for src in evidence.sources if src.tier == "primary"
                        )
                        critiques = evaluate_dossier(
                            critic_input,
                            supporting_evidence_count=len(evidence.evidence_records),
                            contradicting_evidence_count=len(
                                evidence.contradicting_evidence_records
                            ),
                            primary_source_count=primary_source_count,
                        )
                        for critique in critiques:
                            yield AgentEvent(
                                type="critic_persona_critique",
                                run_id=run.id,
                                data={
                                    "dossier_id": dossier_record.dossier_id,
                                    "ticker": dossier_record.ticker,
                                    "persona": critique.persona,
                                    "verdict": critique.verdict,
                                    "rationale": critique.rationale,
                                    "metadata": critique.metadata,
                                },
                            )
                        aggregated = aggregate_critiques(critiques)
                        applied_penalty = 0.0
                        if aggregated["final"] == "reject":
                            hypothesis = await default_research_store.get_hypothesis(
                                hypothesis_id
                            )
                            if hypothesis is not None:
                                point = apply_critic_penalty(
                                    hypothesis,
                                    dossier_id=dossier_record.dossier_id,
                                )
                                await default_research_store.upsert_hypothesis(
                                    hypothesis
                                )
                                applied_penalty = point.delta
                                yield AgentEvent(
                                    type="hypothesis_confidence_updated",
                                    run_id=run.id,
                                    data={
                                        "hypothesis_id": hypothesis_id,
                                        "prev_confidence": round(
                                            point.confidence - point.delta, 4
                                        ),
                                        "new_confidence": point.confidence,
                                        "delta": point.delta,
                                        "evidence_id": point.evidence_id,
                                        "kind": "critic_penalty",
                                        "method": point.method,
                                    },
                                )
                        yield AgentEvent(
                            type="critic_aggregated",
                            run_id=run.id,
                            data={
                                "dossier_id": dossier_record.dossier_id,
                                "ticker": dossier_record.ticker,
                                "final": aggregated["final"],
                                "vote_summary": aggregated["vote_summary"],
                                "hypothesis_id": hypothesis_id,
                                "applied_penalty": applied_penalty,
                            },
                        )
                if decision == "queue_mode_a":
                    yield AgentEvent(
                        type="research_task_created",
                        run_id=run.id,
                        data={
                            "loop_index": loop_index,
                            "ticker": company["ticker"],
                            "task_id": task_record.task_id if task_record else None,
                            "task": (
                                f"Start Mode A underwriting for {company['name']} "
                                f"from {layer.name} frontier."
                            ),
                            "owner": "shinkai",
                            "mode": "mode_a_company",
                            "autonomous": True,
                            "requires_human_approval": True,
                        },
                    )

            evidence_gap = (
                "source-backed evidence found"
                if evidence.source_backed
                else "real external evidence not yet fetched"
            )
            yield AgentEvent(
                type="review_completed",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "layer": layer.name,
                    "findings": [
                        "frontier expanded from mega-cap seed companies",
                        "candidates are linked to a concrete bottleneck",
                        evidence_gap,
                    ],
                    "review_score": 0.78 if evidence.source_backed else 0.64,
                    "optimize_required": not evidence.source_backed,
                },
            )
            yield AgentEvent(
                type="role_step_completed",
                run_id=run.id,
                data={
                    "role": "reviewer",
                    "step": "claim_evidence_review",
                    "loop_index": loop_index,
                    "frontier_id": frontier_item.frontier_id,
                    "verification": assessment.verification,
                    "status": assessment.status,
                    "primary_source_count": assessment.primary_source_count,
                    "contradicting_source_count": assessment.contradicting_source_count,
                    "rationale": assessment.rationale,
                },
            )
            yield AgentEvent(
                type="memory_patch_proposed",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "kind": "research_memory",
                    "proposal": (
                        f"Remember {layer.name} as an AI supply-chain frontier "
                        f"linked to {layer.seed_giants}."
                    ),
                    "requires_human_approval": True,
                },
            )
            yield AgentEvent(
                type="filter_policy_patch_proposed",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "proposal": (
                        "Candidates need both bottleneck linkage and at least one "
                        "source-backed evidence item before Mode A promotion."
                    ),
                    "requires_human_approval": True,
                },
            )
            yield AgentEvent(
                type="checklist_patch_proposed",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "proposal": (
                        "Add an underwriting item that tests whether the AI exposure "
                        "is direct, durable, and margin-accretive."
                    ),
                    "requires_human_approval": True,
                },
            )
            queue_update = frontier_queue.reprioritize_after_review(frontier_item, assessment)
            if frontier_item.status == "running":
                frontier_queue.complete(frontier_item)
            yield AgentEvent(
                type="frontier_reprioritized",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    **queue_update,
                    "completed_count": frontier_queue.completed_count,
                    "queue": frontier_queue.snapshot(),
                },
            )
            yield AgentEvent(
                type="role_step_completed",
                run_id=run.id,
                data={
                    "role": "optimizer",
                    "step": "frontier_queue_reprioritized",
                    "loop_index": loop_index,
                    **queue_update,
                },
            )
            yield AgentEvent(
                type="optimization_decision",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "decision": "continue_deeper",
                    "next_frontier": queue_update.get("next_frontier") or layer.next_frontier,
                    "policy_patch": (
                        "Spiral 2 must replace AgentInference evidence with "
                        "web/filing/transcript sources."
                    ),
                },
            )
            yield AgentEvent(
                type="research_task_created",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "task": (
                        f"Underwrite top candidates in {layer.name}; validate "
                        "Q1/Q2 with primary sources."
                    ),
                    "owner": "shinkai",
                    "mode": "mode_a_company",
                    "autonomous": True,
                },
            )
            yield AgentEvent(
                type="graph_delta",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "summary": delta.summary,
                    "nodes_added": len(delta.nodes),
                    "edges_added": len(delta.edges),
                    "graph_contract": (
                        "Entity/Claim/Evidence nodes plus structural/evidential edges"
                    ),
                },
            )

        async for ack_event in self._consume_pending_injections(
            run,
            consumed_injection_ids,
            frontier_queue=frontier_queue,
            filter_policy_patches=filter_policy_patches,
            current_layer_name=current_layer_name,
        ):
            yield ack_event

        exhausted = max_loops < len(planned_layers)
        yield AgentEvent(
            type="eval_completed",
            run_id=run.id,
            data={
                "process_score": 0.76,
                "evidence_score": 0.38,
                "reasoning_score": 0.68,
                "discovery_score": 0.7,
                "claim_score": 0.62,
                "source_quality_score": 0.46,
                "candidate_dossier_score": 0.82,
                "status": "needs_real_search" if exhausted is False else "budget_exhausted",
                "planner": "deepseek" if planner_payload else "deterministic",
                "next_spiral": "integrate web_search/web_extract primary-source evidence",
            },
        )
        yield AgentEvent(
            type="done",
            run_id=run.id,
            data={
                "status": "autonomous_supply_chain_spiral_1_complete",
                "loops_completed": max_loops,
                "budget_exhausted": exhausted,
            },
        )

    async def _seed_consumed_injection_ids(self, run_id: str) -> set[str]:
        """Seed the set of already-acknowledged injection ids so a recovered run does not
        re-acknowledge injections that were acknowledged before the previous crash."""
        current = await default_run_store.get(run_id)
        return {
            str(event.data.get("injection_id", ""))
            for event in current.events
            if event.type == "injection_acknowledged" and event.data.get("injection_id")
        }

    async def _consume_pending_injections(
        self,
        run: Run,
        consumed_injection_ids: set[str],
        *,
        frontier_queue: FrontierQueue,
        filter_policy_patches: list[str],
        current_layer_name: list[str | None],
    ) -> AsyncIterator[AgentEvent]:
        """Read unconsumed human_injection events, apply their effect to harness
        state, and yield acknowledgment events.

        Each injection is acknowledged exactly once. The effect depends on intent:
          - question: push a FrontierItem so the queue snapshot shows it.
          - constraint: append the note to filter_policy_patches (consulted in
            candidate scoring).
          - correction: apply a confidence penalty to the current layer's
            hypothesis (persisted via research_store).
          - guidance: recorded only; no state change (no clear executable
            semantics in V0 — reserved for reviewer/optimizer phase).

        Effects on in-memory state (frontier_queue, filter_policy_patches) are
        not preserved across run recovery. Hypothesis corrections are persisted
        via the research store and therefore survive recovery.
        """
        run_id = run.id
        current = await default_run_store.get(run_id)
        for event in current.events:
            if event.type != "human_injection":
                continue
            injection_id = event.event_id
            if injection_id in consumed_injection_ids:
                continue
            consumed_injection_ids.add(injection_id)
            intent = str(event.data.get("intent", "guidance"))
            note = str(event.data.get("note", "")).strip()
            if not note:
                yield AgentEvent(
                    type="injection_acknowledged",
                    run_id=run_id,
                    data={
                        "injection_id": injection_id,
                        "intent": intent,
                        "adopted": False,
                        "applied_to": "none",
                        "effect_summary": "ignored: note was empty",
                    },
                )
                continue

            applied_to: str
            effect_summary: str
            extras: dict = {}

            if intent == "question":
                frontier_id = f"human::question::{injection_id}"
                frontier_queue.push(
                    FrontierItem(
                        frontier_id=frontier_id,
                        name=note[:80],
                        priority=0.85,
                        confidence=0.5,
                        expected_value=0.6,
                        estimated_cost=0.5,
                        reason=f"human_injection: {note[:120]}",
                        source="human_injection",
                    )
                )
                applied_to = "frontier"
                effect_summary = (
                    f"queued in frontier as {frontier_id} (priority 0.85); "
                    "awaiting reviewer to schedule"
                )
                extras["frontier_id"] = frontier_id

            elif intent == "constraint":
                if note not in filter_policy_patches:
                    filter_policy_patches.append(note)
                applied_to = "filter"
                effect_summary = (
                    f"appended to filter_policy_patches ({len(filter_policy_patches)} total)"
                )
                extras["filter_policy_patches_count"] = len(filter_policy_patches)

            elif intent == "correction":
                layer = current_layer_name[0]
                if layer is None:
                    applied_to = "none"
                    effect_summary = "no active layer; correction recorded for next layer"
                else:
                    hypothesis_id = _stable_id("hyp", run_id, layer)
                    hypothesis = await default_research_store.get_hypothesis(hypothesis_id)
                    if hypothesis is None:
                        applied_to = "none"
                        effect_summary = (
                            f"no hypothesis found for layer {layer}; correction noted only"
                        )
                    else:
                        point = apply_human_correction(hypothesis, injection_id=injection_id)
                        await default_research_store.upsert_hypothesis(hypothesis)
                        yield AgentEvent(
                            type="hypothesis_confidence_updated",
                            run_id=run_id,
                            data={
                                "hypothesis_id": hypothesis_id,
                                "prev_confidence": round(
                                    point.confidence - point.delta, 4
                                ),
                                "new_confidence": point.confidence,
                                "delta": point.delta,
                                "evidence_id": point.evidence_id,
                                "kind": point.kind,
                                "method": point.method,
                            },
                        )
                        applied_to = "hypothesis"
                        effect_summary = (
                            f"applied confidence penalty to {hypothesis_id} "
                            f"(delta {point.delta})"
                        )
                        extras["hypothesis_id"] = hypothesis_id
                        extras["delta"] = point.delta

            else:  # guidance
                applied_to = "none"
                effect_summary = (
                    "recorded only; guidance has no V0 executable effect "
                    "(reserved for reviewer/optimizer phase)"
                )

            yield AgentEvent(
                type="injection_acknowledged",
                run_id=run_id,
                data={
                    "injection_id": injection_id,
                    "intent": intent,
                    "note": note,
                    "adopted": applied_to != "none",
                    "applied_to": applied_to,
                    "effect_summary": effect_summary,
                    **extras,
                },
            )

    async def _plan_with_deepseek(self, run: Run) -> dict:
        client = DeepSeekClient(
            api_key=settings.deepseek_api_key or "",
            base_url=settings.deepseek_base_url,
            model=settings.llm_model,
        )
        theme = str(run.anchor or "").strip() or "AI infrastructure"
        objective = str(
            run.scope.get(
                "objective",
                "discover under-covered second-order suppliers in this theme",
            )
        ).strip()
        system = (
            "You are shinkai's autonomous investment research planner. Given a "
            "user-supplied investment theme, propose 3-5 *concrete supply-chain "
            "layers* that sit one or two steps removed from the obvious mega-cap "
            "winners. For each layer, identify the structural bottleneck and "
            "3-5 candidate US-listed second-order suppliers that may be "
            "under-covered by sell-side. Return strict JSON only — no commentary."
        )
        user = (
            f"Theme: {theme}\n"
            f"Objective: {objective}\n\n"
            "Output JSON with this exact shape:\n"
            "{\n"
            '  "frontiers": [\n'
            "    {\n"
            '      "name": "specific layer name, not the theme itself",\n'
            '      "seed_giants": ["NVDA", "..." ],   // mega-caps that sit upstream\n'
            '      "bottleneck": "one-sentence structural constraint",\n'
            '      "evidence_stub": "what primary-source evidence would confirm this",\n'
            '      "companies": [\n'
            '        {"ticker":"AAAA","name":"Co name","quality":0.55,"underwater":0.62}\n'
            "      ],\n"
            '      "next_frontier": "where deeper research should head next"\n'
            "    }\n"
            "  ],\n"
            '  "review_policy": ["concrete review rule"],\n'
            '  "optimization_policy_patch": "one-line policy note"\n'
            "}\n\n"
            "Hard constraints (your output will be rejected if violated):\n"
            "- 3 to 6 frontiers, no more.\n"
            "- Each frontier MUST have a non-empty bottleneck and next_frontier.\n"
            "- Each frontier MUST contain at least 3 companies.\n"
            "- Tickers MUST be US-listed and look like real symbols "
            "(1-5 uppercase letters, optional trailing digit).\n"
            "- DO NOT propose layers that are themselves megacaps "
            "(no \"NVIDIA accelerators\", \"Microsoft cloud\", etc.). "
            "Layers must describe sub-suppliers, components, or constrained "
            "capacity — not end products.\n"
            "- quality/underwater are 0..1; underwater higher means less "
            "sell-side coverage."
        )
        return await client.chat_json(system=system, user=user, temperature=0.4)

    def _validate_planner_payload(
        self, payload: dict
    ) -> tuple[list[SupplyChainLayer], str | None]:
        """Validate the LLM planner output and return ``(layers, reject_reason)``.

        ``reject_reason`` is ``None`` on success. On failure, ``layers`` is
        empty and ``reject_reason`` describes why so the caller can decide
        whether to fall back to ``AI_SUPPLY_CHAIN_LAYERS`` or fail the run
        (``force_llm_planner``).
        """
        frontiers = payload.get("frontiers", [])
        if not isinstance(frontiers, list):
            return [], "frontiers is not a list"
        if len(frontiers) < 3:
            return [], f"need at least 3 frontiers, got {len(frontiers)}"

        layers: list[SupplyChainLayer] = []
        for item in frontiers[:6]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            bottleneck = str(item.get("bottleneck") or "").strip()
            next_frontier = str(item.get("next_frontier") or "").strip()
            if not (name and bottleneck and next_frontier):
                continue
            evidence_stub = str(item.get("evidence_stub") or "").strip()
            if not evidence_stub:
                evidence_stub = f"Validate {name} bottleneck via primary sources."

            companies_raw = item.get("companies", [])
            if not isinstance(companies_raw, list):
                companies_raw = []
            normalized: list[dict[str, object]] = []
            for company in companies_raw[:5]:
                if not isinstance(company, dict):
                    continue
                ticker = str(company.get("ticker") or "").strip().upper()
                cname = str(company.get("name") or ticker).strip()
                if not TICKER_PATTERN.match(ticker) or not cname:
                    continue
                normalized.append(
                    {
                        "ticker": ticker,
                        "name": cname,
                        "quality": _bounded_float(company.get("quality"), default=0.55),
                        "underwater": _bounded_float(
                            company.get("underwater"), default=0.55
                        ),
                    }
                )
            if len(normalized) < 3:
                continue

            seed_giants_raw = item.get("seed_giants", [])
            seed_giants = (
                [str(seed) for seed in seed_giants_raw[:6]]
                if isinstance(seed_giants_raw, list) and seed_giants_raw
                else ["NVIDIA"]
            )
            layers.append(
                SupplyChainLayer(
                    name=name,
                    seed_giants=seed_giants,
                    bottleneck=bottleneck,
                    evidence_stub=evidence_stub,
                    companies=normalized,
                    next_frontier=next_frontier,
                )
            )

        if len(layers) < 3:
            return [], (
                f"only {len(layers)} layer(s) survived validation "
                "(need 3+ with 3+ valid tickers each)"
            )
        return layers, None

    async def _run_web_search(self, query: str) -> ToolResult:
        tool = default_tool_registry.get("web_search")
        return await tool.run(query=query, max_results=3)

    async def _run_web_extract(self, url: str) -> ToolResult:
        tool = default_tool_registry.get("web_extract")
        return await tool.run(url=url)

    async def _validate_ticker_safely(self, ticker: str) -> dict | None:
        """Resolve a ticker via the validator tool. Returns the payload dict
        or None when the tool is not registered. Never raises.
        """
        try:
            tool = default_tool_registry.get("ticker_validate")
        except KeyError:
            return None
        try:
            result = await tool.run(ticker=ticker)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(result.data, dict):
            return None
        return result.data

    async def _sec_filings_evidence(
        self,
        ticker: str,
        run_id: str,
        layer_name: str,
    ) -> tuple[list[SourceRef], list[Evidence]] | None:
        """Pull recent 10-K / 10-Q filings for ``ticker`` and convert them to
        primary-tier SourceRef + Evidence records ready to be merged into the
        layer's evidence pool. Returns None on any failure so the harness can
        continue with synthetic / web evidence alone.
        """
        try:
            tool = default_tool_registry.get("sec_filings")
        except KeyError:
            return None
        try:
            result = await tool.run(ticker=ticker, limit=4)
        except Exception:  # noqa: BLE001
            return None
        if not result.ok or not isinstance(result.data, dict):
            return None
        filings = result.data.get("filings") or []
        if not filings:
            return None
        company_name = str(result.data.get("company_name") or ticker)
        sources: list[SourceRef] = []
        evidence_records: list[Evidence] = []
        for filing in filings:
            if not isinstance(filing, dict):
                continue
            accession = str(filing.get("accession") or "")
            form = str(filing.get("form") or "")
            url = str(filing.get("primary_document_url") or "")
            filed_at = str(filing.get("filed_at") or "")
            description = str(filing.get("primary_document_description") or "")
            if not (url and accession):
                continue
            source_id = _stable_id("source", "sec", ticker, accession)
            evidence_id = _stable_id("evidence", run_id, "sec", ticker, accession)
            source = SourceRef(
                source_id=source_id,
                type="sec",
                tier="primary",
                url=url,
                title=f"{company_name} · {form} ({filed_at})",
                publisher="SEC EDGAR",
                primary_source_flag=True,
                reliability=0.9,
                metadata={
                    "run_id": run_id,
                    "ticker": ticker,
                    "form": form,
                    "accession": accession,
                },
            )
            evidence_record = Evidence(
                evidence_id=evidence_id,
                source_id=source_id,
                run_id=run_id,
                kind="filing_fact",
                text=description or f"{form} filed {filed_at}",
                url=url,
                summary=f"{form} filing for {company_name} on {filed_at}",
                citation_url=url,
                citation_label=f"{ticker} {form} {filed_at}",
                confidence=0.7,
                metadata={
                    "layer": layer_name,
                    "ticker": ticker,
                    "form": form,
                    "filed_at": filed_at,
                },
            )
            sources.append(source)
            evidence_records.append(evidence_record)
        return (sources, evidence_records) if evidence_records else None

    async def _persist_research_records(
        self,
        *,
        evidence: LayerEvidence,
        claims: list[Claim],
        candidates: list[CandidateCompany],
        dossiers: list[CompanyDossier],
        tasks: list[ResearchTask],
    ) -> None:
        for source in evidence.sources:
            await default_research_store.upsert_source(source)
        for source in evidence.contradicting_sources:
            await default_research_store.upsert_source(source)
        for record in evidence.evidence_records:
            await default_research_store.upsert_evidence(record)
        for record in evidence.contradicting_evidence_records:
            await default_research_store.upsert_evidence(record)
        for claim in claims:
            await default_research_store.upsert_claim(claim)
        for candidate in candidates:
            await default_research_store.upsert_candidate(candidate)
        for dossier in dossiers:
            await default_research_store.upsert_dossier(dossier)
        for task in tasks:
            await default_research_store.upsert_task(task)

    def _conflicting_source_ids(
        self,
        layer: SupplyChainLayer,
        evidence: LayerEvidence,
    ) -> list[str]:
        conflict_markers = [
            f"{layer.name.lower()} is not a bottleneck",
            "not a bottleneck",
            "no supply constraint",
            "no material constraint",
            "demand is declining",
        ]
        source_ids: list[str] = []
        for record in evidence.evidence_records:
            text = f"{record.text} {record.summary}".lower()
            if any(marker in text for marker in conflict_markers):
                source_ids.append(record.source_id)
        return source_ids

    def _evidence_from_tool_results(
        self,
        layer: SupplyChainLayer,
        run_id: str,
        query: str,
        search_result: ToolResult,
        extract_result: ToolResult | None,
        contradiction_query: str = "",
        contradiction_search_result: ToolResult | None = None,
    ) -> LayerEvidence:
        if not search_result.ok:
            return self._stub_evidence(layer, run_id, tool_result=search_result)
        results = search_result.data.get("results", [])
        if not isinstance(results, list) or not results:
            return self._stub_evidence(layer, run_id, tool_result=search_result)
        first = results[0]
        if not isinstance(first, dict):
            return self._stub_evidence(layer, run_id, tool_result=search_result)
        title = str(first.get("title") or "Web evidence")
        url = str(first.get("url") or "")
        snippet = str(first.get("snippet") or layer.evidence_stub)
        extracted_title = ""
        extracted_excerpt = ""
        extraction_error = ""
        if extract_result:
            if extract_result.ok:
                extracted_title = str(extract_result.data.get("title") or "")
                extracted_excerpt = str(extract_result.data.get("excerpt") or "")
            else:
                extraction_error = extract_result.error or extract_result.summary
        excerpt = extracted_excerpt or snippet or title
        node = Node(
            id=node_id("evidence", f"{layer.name} {url or excerpt}"),
            type="Evidence",
            label=f"Source evidence: {layer.name}",
            confidence=0.78 if extracted_excerpt else 0.72,
            source_refs=[],
            data={
                "excerpt": excerpt,
                "source_uri": url,
                "source_title": extracted_title or title,
                "source_kind": "WebExtract" if extracted_excerpt else "WebSearchResult",
                "reliability": 4 if extracted_excerpt else 3,
                "needs_real_source": False,
                "query": query,
                "search_snippet": snippet,
                "extraction_error": extraction_error,
            },
            tags=[
                "source-backed",
                "spiral-2",
                "extracted" if extracted_excerpt else "search-result",
            ],
        )
        sources: list[SourceRef] = []
        evidence_records: list[Evidence] = []
        for index, result in enumerate(results[:3], start=1):
            if not isinstance(result, dict):
                continue
            result_url = str(result.get("url") or "").strip()
            result_title = str(result.get("title") or "Web evidence").strip()
            result_snippet = str(result.get("snippet") or "").strip()
            result_excerpt = excerpt if index == 1 else result_snippet or result_title
            tier = classify_source_tier("web", result_url, _publisher_from_url(result_url))
            extracted = index == 1 and bool(extracted_excerpt)
            is_aggregator = bool(result.get("is_aggregator"))
            source = SourceRef(
                source_id=_stable_id("source", result_url or result_title, layer.name),
                type="web",
                tier=tier,
                url=result_url,
                title=result_title,
                publisher=_publisher_from_url(result_url),
                primary_source_flag=tier == "primary" and not is_aggregator,
                reliability=source_reliability_score(
                    tier, extracted=extracted, is_aggregator=is_aggregator
                ),
                metadata={
                    "run_id": run_id,
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "source_backed": True,
                    "is_aggregator": is_aggregator,
                },
            )
            record = Evidence(
                evidence_id=_stable_id("evidence", run_id, layer.name, result_url or result_title),
                source_id=source.source_id,
                run_id=run_id,
                kind="web_extract" if index == 1 and extracted_excerpt else "summary",
                text=result_excerpt,
                url=result_url,
                quote=_quote_from_excerpt(result_excerpt),
                summary=result_snippet or result_excerpt[:240],
                citation_url=result_url,
                citation_anchor=_citation_anchor(index),
                citation_label=f"{result_title}#{index}",
                confidence=0.78 if index == 1 and extracted_excerpt else 0.66,
                metadata={
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "source_title": result_title,
                    "extraction_error": extraction_error if index == 1 else "",
                },
            )
            sources.append(source)
            evidence_records.append(record)
        contradicting_sources, contradicting_records = self._contradicting_records_from_search(
            layer,
            run_id,
            contradiction_query,
            contradiction_search_result,
        )
        node.source_refs = [record.evidence_id for record in evidence_records]
        return LayerEvidence(
            node=node,
            source_backed=True,
            sources=sources,
            evidence_records=evidence_records,
            contradicting_sources=contradicting_sources,
            contradicting_evidence_records=contradicting_records,
            tool_result=search_result,
            extract_result=extract_result,
        )

    def _contradicting_records_from_search(
        self,
        layer: SupplyChainLayer,
        run_id: str,
        query: str,
        search_result: ToolResult | None,
    ) -> tuple[list[SourceRef], list[Evidence]]:
        if not search_result or not search_result.ok:
            return [], []
        results = search_result.data.get("results", [])
        if not isinstance(results, list):
            return [], []
        sources: list[SourceRef] = []
        records: list[Evidence] = []
        for index, result in enumerate(results[:3], start=1):
            if not isinstance(result, dict):
                continue
            result_url = str(result.get("url") or "").strip()
            result_title = str(result.get("title") or "Contradicting web evidence").strip()
            result_snippet = str(result.get("snippet") or "").strip()
            text = f"{result_title} {result_snippet}"
            if not _looks_contradictory(text):
                continue
            publisher = _publisher_from_url(result_url)
            tier = classify_source_tier("web", result_url, publisher)
            is_aggregator = bool(result.get("is_aggregator"))
            source = SourceRef(
                source_id=_stable_id("source", "refute", result_url or result_title, layer.name),
                type="web",
                tier=tier,
                url=result_url,
                title=result_title,
                publisher=publisher,
                primary_source_flag=tier == "primary" and not is_aggregator,
                reliability=source_reliability_score(tier, is_aggregator=is_aggregator),
                metadata={
                    "run_id": run_id,
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "polarity": "contradict",
                    "is_aggregator": is_aggregator,
                },
            )
            record = Evidence(
                evidence_id=_stable_id(
                    "evidence",
                    run_id,
                    layer.name,
                    "refute",
                    result_url or result_title,
                ),
                source_id=source.source_id,
                run_id=run_id,
                kind="summary",
                text=result_snippet or result_title,
                url=result_url,
                quote=_quote_from_excerpt(result_snippet or result_title),
                summary=result_snippet or result_title,
                citation_url=result_url,
                citation_anchor=_citation_anchor(index),
                citation_label=f"{result_title}#{index}",
                confidence=source.reliability,
                metadata={
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "polarity": "contradict",
                    "source_title": result_title,
                },
            )
            sources.append(source)
            records.append(record)
        return sources, records

    def _stub_evidence(
        self,
        layer: SupplyChainLayer,
        run_id: str,
        tool_result: ToolResult | None = None,
    ) -> LayerEvidence:
        source = SourceRef(
            source_id=_stable_id("source", run_id, layer.name, "agent-inference"),
            type="manual",
            tier="agent_inference",
            url="",
            title=f"Agent inference stub: {layer.name}",
            publisher="shinkai",
            primary_source_flag=False,
            reliability=0.2,
            metadata={
                "run_id": run_id,
                "layer": layer.name,
                "source_backed": False,
                "needs_real_source": True,
            },
        )
        record = Evidence(
            evidence_id=_stable_id("evidence", run_id, layer.name, "agent-inference"),
            source_id=source.source_id,
            run_id=run_id,
            kind="summary",
            text=layer.evidence_stub,
            quote=_quote_from_excerpt(layer.evidence_stub),
            summary=layer.evidence_stub,
            citation_label=f"Agent inference: {layer.name}",
            confidence=0.35,
            metadata={
                "layer": layer.name,
                "source_backed": False,
                "needs_real_source": True,
                "tool_error": tool_result.error if tool_result else "",
            },
        )
        node = Node(
            id=node_id("evidence", layer.evidence_stub),
            type="Evidence",
            label=f"Evidence stub: {layer.name}",
            confidence=0.5,
            source_refs=[record.evidence_id],
            data={
                "excerpt": layer.evidence_stub,
                "source_kind": "AgentInference",
                "reliability": 2,
                "needs_real_source": True,
            },
            tags=["needs-source", "spiral-1"],
        )
        return LayerEvidence(
            node=node,
            source_backed=False,
            sources=[source],
            evidence_records=[record],
            contradicting_sources=[],
            contradicting_evidence_records=[],
            tool_result=tool_result,
        )

    def _evidence_query(self, layer: SupplyChainLayer) -> str:
        seeds = " ".join(layer.seed_giants[:3])
        return (
            f"{layer.name} AI data center supply chain bottleneck {seeds} "
            f"{_SOURCE_QUALITY_HINT}"
        )

    def _contradiction_query(self, layer: SupplyChainLayer) -> str:
        seeds = " ".join(layer.seed_giants[:3])
        return (
            f"{layer.name} AI data center not a bottleneck demand decline "
            f"margin pressure supply constraint refute {seeds} "
            f"{_SOURCE_QUALITY_HINT}"
        )


def _bounded_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


def _frontier_items_from_layers(layers: list[SupplyChainLayer]) -> list[FrontierItem]:
    items: list[FrontierItem] = []
    seen_ids: set[str] = set()
    for index, layer in enumerate(layers):
        expected_value = min(1.0, 0.56 + len(layer.companies) * 0.07)
        confidence = 0.62 + min(0.18, len(layer.seed_giants) * 0.03)
        cost = 0.34 + min(0.24, len(layer.companies) * 0.04)
        priority = min(1.0, 0.64 + (0.04 if index == 0 else 0.0))
        frontier_id = _stable_id("frontier", layer.name, layer.bottleneck)
        if frontier_id in seen_ids:
            frontier_id = _stable_id("frontier", layer.name, layer.bottleneck, str(index))
        seen_ids.add(frontier_id)
        items.append(
            FrontierItem(
                frontier_id=frontier_id,
                name=layer.name,
                priority=priority,
                confidence=confidence,
                expected_value=expected_value,
                estimated_cost=cost,
                reason=(
                    "seeded by AI mega-cap demand and concrete second-order "
                    "candidate coverage"
                ),
                source="deterministic_planner",
                next_frontier=layer.next_frontier,
            )
        )
    return items


def _stable_id(prefix: str, *values: object) -> str:
    raw = "||".join(str(value) for value in values)
    digest = sha1(raw.encode("utf-8")).hexdigest()[:12]
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in raw[:40]).strip("_")
    return f"{prefix}_{safe[:32]}_{digest}"


def _publisher_from_url(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.removeprefix("www.")


def _candidate_risk_flags(
    quality_pass: bool,
    under_coverage_pass: bool,
    source_backed: bool,
) -> list[str]:
    flags: list[str] = []
    if not quality_pass:
        flags.append("quality_filter_not_confirmed")
    if not under_coverage_pass:
        flags.append("market_attention_may_be_consensus")
    if not source_backed:
        flags.append("needs_primary_source_validation")
    return flags


def _candidate_questions(company_name: str, layer_name: str) -> list[str]:
    return [
        f"What share of {company_name}'s revenue is directly exposed to {layer_name}?",
        "Is the AI-linked demand durable across a full cycle?",
        "Does the exposure improve margins rather than only revenue growth?",
    ]


def _build_company_dossier(
    *,
    run_id: str,
    layer: SupplyChainLayer,
    candidate: CandidateCompany,
    score: float,
    q1_pass: bool,
    q2_pass: bool,
    assessment: ClaimAssessment,
) -> CompanyDossier:
    directness = assessment.verification == "support"
    margin_check = candidate.quality_score >= 0.68
    valuation_check = candidate.under_coverage_score >= 0.55
    risk_check = assessment.verification != "refute" and "needs_primary_source_validation" not in (
        candidate.risk_flags
    )
    decision, rationale = _mode_a_decision(
        score=score,
        quality=q1_pass,
        undercovered=q2_pass,
        directness=directness,
        margin=margin_check,
        valuation=valuation_check,
        risk=risk_check,
    )
    return CompanyDossier(
        dossier_id=_stable_id("dossier", run_id, candidate.ticker, layer.name),
        run_id=run_id,
        candidate_id=candidate.candidate_id,
        ticker=candidate.ticker,
        company_name=candidate.name,
        supply_chain_layer=layer.name,
        business_summary=(
            f"{candidate.name} is being evaluated as a second-order supplier tied to "
            f"{layer.name}."
        ),
        ai_exposure=candidate.thesis,
        supply_chain_position=layer.bottleneck,
        financial_metrics={
            "quality_score": candidate.quality_score,
            "under_coverage_score": candidate.under_coverage_score,
            "relevance_score": candidate.relevance_score,
            "primary_source_count": assessment.primary_source_count,
            "claim_confidence": assessment.confidence,
        },
        valuation_view=(
            "Potentially under-covered relative to bottleneck relevance."
            if q2_pass
            else "Coverage may already reflect part of the AI exposure."
        ),
        risk_factors=[
            *candidate.risk_flags,
            *([] if assessment.verification != "refute" else ["refuting_evidence_present"]),
            *([] if assessment.primary_source_count else ["primary_source_gap"]),
        ],
        catalysts=[
            f"Primary-source confirmation of {layer.name} demand",
            "AI-linked order commentary or backlog disclosure",
            "Margin evidence from mix shift rather than only revenue growth",
        ],
        mode_a_checks={
            "quality": q1_pass,
            "undercovered": q2_pass,
            "direct_ai_exposure": directness,
            "margin_accretive": margin_check,
            "valuation_reasonable": valuation_check,
            "risk_not_refuted": risk_check,
        },
        decision=decision,
        decision_rationale=rationale,
        claim_ids=candidate.claim_ids,
        evidence_ids=candidate.evidence_ids,
        metadata={
            "assessment": assessment.model_dump(mode="json"),
            "source": "mode_a_dossier_builder",
        },
    )


def _mode_a_decision(
    *,
    score: float,
    quality: bool,
    undercovered: bool,
    directness: bool,
    margin: bool,
    valuation: bool,
    risk: bool,
) -> tuple[str, str]:
    if not risk or not quality:
        return "reject", "Rejected until risk is resolved and the quality filter passes."
    if all([quality, undercovered, directness, margin, valuation]) and score >= 0.67:
        return "invest", "All Mode A checks pass with source-backed exposure."
    return "watch", "Watchlist until directness, valuation, or margin evidence is stronger."


def _stale_evidence_ids(evidence: LayerEvidence, stale_source_ids: list[str]) -> list[str]:
    stale_sources = set(stale_source_ids)
    return [
        record.evidence_id
        for record in evidence.evidence_records
        if record.source_id in stale_sources
    ]


def _quote_from_excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:280]


def _citation_anchor(index: int) -> str:
    return f"result-{index}"


def _looks_contradictory(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "not a bottleneck",
        "no bottleneck",
        "no supply constraint",
        "not constrained",
        "demand decline",
        "demand is declining",
        "margin pressure",
        "oversupply",
        "capacity glut",
    ]
    return any(marker in lowered for marker in markers)


def _first_result_url(result: ToolResult) -> str:
    """Pick the URL to send through web_extract.

    Prefers the first non-aggregator result so we don't waste an extract
    call on stocktitan / marketbeat / seekingalpha rewrites. Falls back to
    results[0] when every result is flagged as aggregator (still better to
    extract something than nothing). Noise sources never appear here —
    they are dropped earlier in WebSearchTool.
    """
    results = result.data.get("results", [])
    if not result.ok or not isinstance(results, list) or not results:
        return ""
    for entry in results:
        if not isinstance(entry, dict):
            continue
        if entry.get("is_aggregator"):
            continue
        url = str(entry.get("url") or "").strip()
        if url:
            return url
    first = results[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("url") or "").strip()
