from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha1
from urllib.parse import urlparse

from shinkai_api.core.config import settings
from shinkai_api.graph import Edge, GraphDelta, Node, default_graph_store, edge_id, node_id
from shinkai_api.llm import DeepSeekClient, DeepSeekError
from shinkai_api.research import (
    CandidateCompany,
    Claim,
    Evidence,
    ResearchTask,
    SourceRef,
    assess_claim_support,
    classify_source_tier,
    default_research_store,
    source_reliability_score,
)
from shinkai_api.runs.models import Run
from shinkai_api.schemas.events import AgentEvent
from shinkai_api.tools import default_tool_registry
from shinkai_api.tools.base import ToolResult


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
        planned_layers = list(AI_SUPPLY_CHAIN_LAYERS)
        planner_payload: dict | None = None
        if settings.deepseek_api_key:
            yield AgentEvent(
                type="tool_call",
                run_id=run.id,
                data={
                    "name": "deepseek_frontier_planner",
                    "args": {"model": settings.llm_model, "objective": run.scope.get("objective")},
                    "autonomous": True,
                },
            )
            try:
                planner_payload = await self._plan_with_deepseek(run, planned_layers)
                planned_layers.extend(self._layers_from_planner_payload(planner_payload))
                usage = planner_payload.get("_usage", {})
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "deepseek_frontier_planner",
                        "ok": True,
                        "summary": "DeepSeek proposed additional frontiers and review policy.",
                        "preview": {
                            "frontiers": len(planner_payload.get("frontiers", [])),
                            "usage": usage,
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
                yield AgentEvent(
                    type="tool_result",
                    run_id=run.id,
                    data={
                        "name": "deepseek_frontier_planner",
                        "ok": False,
                        "error": str(exc),
                        "fallback": "deterministic_supply_chain_layers",
                    },
                )

        max_loops = min(len(planned_layers), max(1, run.budget.max_tool_calls // 20))
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
            },
        )

        live_sources = bool(run.scope.get("allow_live_sources", True))

        for loop_index, layer in enumerate(planned_layers[:max_loops], start=1):
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
            task_records: list[ResearchTask] = []
            for company in layer.companies:
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
                        supporting_evidence_ids=evidence_ids,
                        evidence_ids=evidence_ids,
                        contradicting_evidence_ids=contradicting_evidence_ids,
                        stale_evidence_ids=_stale_evidence_ids(
                            evidence,
                            assessment.stale_source_ids,
                        ),
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
            yield AgentEvent(
                type="judgment_created",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "judgment": (
                        f"{layer.name} is a candidate AI infrastructure bottleneck "
                        "where second-order suppliers may be more under-covered than seed giants."
                    ),
                    "confidence": 0.66,
                    "support": [layer.bottleneck],
                },
            )

            for company in layer.companies:
                quality = float(company["quality"])
                underwater = float(company["underwater"])
                score = round((quality * 0.55) + (underwater * 0.45), 3)
                q1_pass = quality >= 0.65
                q2_pass = underwater >= 0.55
                decision = "queue_mode_a" if q1_pass and q2_pass and score >= 0.62 else "watch_only"
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
            yield AgentEvent(
                type="optimization_decision",
                run_id=run.id,
                data={
                    "loop_index": loop_index,
                    "decision": "continue_deeper",
                    "next_frontier": layer.next_frontier,
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

        exhausted = max_loops < len(planned_layers)
        yield AgentEvent(
            type="eval_completed",
            run_id=run.id,
            data={
                "process_score": 0.76,
                "evidence_score": 0.38,
                "reasoning_score": 0.68,
                "discovery_score": 0.7,
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

    async def _plan_with_deepseek(
        self,
        run: Run,
        base_layers: list[SupplyChainLayer],
    ) -> dict:
        client = DeepSeekClient(
            api_key=settings.deepseek_api_key or "",
            base_url=settings.deepseek_base_url,
            model=settings.llm_model,
        )
        base_context = [
            {
                "name": layer.name,
                "seed_giants": layer.seed_giants,
                "bottleneck": layer.bottleneck,
                "companies": layer.companies,
                "next_frontier": layer.next_frontier,
            }
            for layer in base_layers
        ]
        system = (
            "You are shinkai's autonomous investment research planner. "
            "Your job is to expand from mega-cap AI consensus companies into "
            "deeper AI supply-chain layers, identify bottlenecks, surface "
            "under-covered candidate companies, and specify review/optimization "
            "rules. Return strict JSON only."
        )
        user = (
            "Objective:\n"
            f"{run.scope.get('objective', 'discover AI supply-chain key companies')}\n\n"
            "Existing deterministic layers:\n"
            f"{base_context}\n\n"
            "Return JSON with this shape:\n"
            "{\n"
            '  "frontiers": [\n'
            "    {\n"
            '      "name": "layer name",\n'
            '      "seed_giants": ["NVIDIA"],\n'
            '      "bottleneck": "specific bottleneck claim",\n'
            '      "evidence_stub": "what evidence should be fetched next",\n'
            '      "companies": [\n'
            '        {"ticker":"ABC","name":"Company","quality":0.6,"underwater":0.6}\n'
            "      ],\n"
            '      "next_frontier": "next deeper search direction"\n'
            "    }\n"
            "  ],\n"
            '  "review_policy": ["rule"],\n'
            '  "optimization_policy_patch": "policy patch"\n'
            "}\n\n"
            "Constraints: avoid obvious mega-cap-only answers; prefer concrete "
            "second-order suppliers; mark uncertain candidates with lower scores; "
            "do not invent more than 3 companies per frontier."
        )
        return await client.chat_json(system=system, user=user, temperature=0.25)

    def _layers_from_planner_payload(self, payload: dict) -> list[SupplyChainLayer]:
        layers: list[SupplyChainLayer] = []
        frontiers = payload.get("frontiers", [])
        if not isinstance(frontiers, list):
            return layers
        for item in frontiers[:4]:
            if not isinstance(item, dict):
                continue
            companies = item.get("companies", [])
            if not isinstance(companies, list):
                companies = []
            normalized_companies = []
            for company in companies[:3]:
                if not isinstance(company, dict):
                    continue
                ticker = str(company.get("ticker") or "").strip().upper()
                name = str(company.get("name") or ticker).strip()
                if not ticker or not name:
                    continue
                normalized_companies.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "quality": _bounded_float(company.get("quality"), default=0.55),
                        "underwater": _bounded_float(company.get("underwater"), default=0.55),
                    }
                )
            if not normalized_companies:
                continue
            seed_giants = item.get("seed_giants")
            if not isinstance(seed_giants, list):
                seed_giants = ["NVIDIA", "Microsoft"]
            layers.append(
                SupplyChainLayer(
                    name=str(item.get("name") or "DeepSeek frontier").strip(),
                    seed_giants=[str(seed) for seed in seed_giants[:6]],
                    bottleneck=str(item.get("bottleneck") or "").strip(),
                    evidence_stub=str(item.get("evidence_stub") or "").strip(),
                    companies=normalized_companies,
                    next_frontier=str(item.get("next_frontier") or "").strip(),
                )
            )
        return [
            layer
            for layer in layers
            if layer.name and layer.bottleneck and layer.evidence_stub and layer.next_frontier
        ]

    async def _run_web_search(self, query: str) -> ToolResult:
        tool = default_tool_registry.get("web_search")
        return await tool.run(query=query, max_results=3)

    async def _run_web_extract(self, url: str) -> ToolResult:
        tool = default_tool_registry.get("web_extract")
        return await tool.run(url=url)

    async def _persist_research_records(
        self,
        *,
        evidence: LayerEvidence,
        claims: list[Claim],
        candidates: list[CandidateCompany],
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
            source = SourceRef(
                source_id=_stable_id("source", result_url or result_title, layer.name),
                type="web",
                tier=tier,
                url=result_url,
                title=result_title,
                publisher=_publisher_from_url(result_url),
                primary_source_flag=tier == "primary",
                reliability=source_reliability_score(tier, extracted=extracted),
                metadata={
                    "run_id": run_id,
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "source_backed": True,
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
            source = SourceRef(
                source_id=_stable_id("source", "refute", result_url or result_title, layer.name),
                type="web",
                tier=tier,
                url=result_url,
                title=result_title,
                publisher=publisher,
                primary_source_flag=tier == "primary",
                reliability=source_reliability_score(tier),
                metadata={
                    "run_id": run_id,
                    "layer": layer.name,
                    "query": query,
                    "rank": index,
                    "polarity": "contradict",
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
        return f"{layer.name} AI data center supply chain bottleneck {seeds}"

    def _contradiction_query(self, layer: SupplyChainLayer) -> str:
        seeds = " ".join(layer.seed_giants[:3])
        return (
            f"{layer.name} AI data center not a bottleneck demand decline "
            f"margin pressure supply constraint refute {seeds}"
        )


def _bounded_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


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
    results = result.data.get("results", [])
    if not result.ok or not isinstance(results, list) or not results:
        return ""
    first = results[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("url") or "").strip()
