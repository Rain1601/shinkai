from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from shinkai_api.core.config import settings
from shinkai_api.graph import Edge, GraphDelta, Node, default_graph_store, edge_id, node_id
from shinkai_api.llm import DeepSeekClient, DeepSeekError
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
                evidence = self._evidence_from_tool_results(
                    layer,
                    search_query,
                    search_result,
                    extract_result,
                )
            else:
                evidence = self._stub_evidence(layer)

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
                data={"statement": layer.bottleneck, "claim_kind": "Qualitative"},
                tags=["bottleneck", "ai-infrastructure"],
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
                    source_refs=[evidence_node.id],
                ),
            ]

            candidate_nodes: list[Node] = []
            candidate_edges: list[Edge] = []
            candidate_detail_nodes: list[Node] = []
            candidate_detail_edges: list[Edge] = []
            for company in layer.companies:
                quality = float(company["quality"])
                underwater = float(company["underwater"])
                score = round((quality * 0.55) + (underwater * 0.45), 3)
                q1_pass = quality >= 0.65
                q2_pass = underwater >= 0.55
                decision = "queue_mode_a" if q1_pass and q2_pass and score >= 0.62 else "watch_only"
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
                    },
                    tags=["candidate", "mode-b"],
                )
                claim_node = Node(
                    id=node_id("claim", f"{company['ticker']} {layer.name} exposure"),
                    type="Claim",
                    label=f"{company['ticker']} bottleneck exposure",
                    confidence=score,
                    source_refs=[evidence_node.id],
                    data={
                        "statement": (
                            f"{company['name']} may be a second-order beneficiary of "
                            f"{layer.name} AI infrastructure constraints."
                        ),
                        "claim_kind": "Forward",
                        "ticker": company["ticker"],
                    },
                    tags=["candidate-claim", "underwriting-input"],
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
                    },
                    tags=["open-question", "mode-a-input"],
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
                            source_refs=[evidence_node.id],
                        ),
                        Edge(
                            id=edge_id(evidence_node.id, "supports", claim_node.id),
                            type="evidential",
                            relation="supports",
                            from_node=evidence_node.id,
                            to_node=claim_node.id,
                            confidence=0.68 if evidence.source_backed else 0.48,
                            source_refs=[evidence_node.id],
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
                        source_refs=[evidence_node.id],
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
                            source_refs=[evidence_node.id],
                        )
                    )

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
                if decision == "queue_mode_a":
                    yield AgentEvent(
                        type="research_task_created",
                        run_id=run.id,
                        data={
                            "loop_index": loop_index,
                            "ticker": company["ticker"],
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

    def _evidence_from_tool_results(
        self,
        layer: SupplyChainLayer,
        query: str,
        search_result: ToolResult,
        extract_result: ToolResult | None,
    ) -> LayerEvidence:
        if not search_result.ok:
            return self._stub_evidence(layer, tool_result=search_result)
        results = search_result.data.get("results", [])
        if not isinstance(results, list) or not results:
            return self._stub_evidence(layer, tool_result=search_result)
        first = results[0]
        if not isinstance(first, dict):
            return self._stub_evidence(layer, tool_result=search_result)
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
            source_refs=[url] if url else [],
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
        return LayerEvidence(
            node=node,
            source_backed=True,
            tool_result=search_result,
            extract_result=extract_result,
        )

    def _stub_evidence(
        self,
        layer: SupplyChainLayer,
        tool_result: ToolResult | None = None,
    ) -> LayerEvidence:
        node = Node(
            id=node_id("evidence", layer.evidence_stub),
            type="Evidence",
            label=f"Evidence stub: {layer.name}",
            confidence=0.5,
            data={
                "excerpt": layer.evidence_stub,
                "source_kind": "AgentInference",
                "reliability": 2,
                "needs_real_source": True,
            },
            tags=["needs-source", "spiral-1"],
        )
        return LayerEvidence(node=node, source_backed=False, tool_result=tool_result)

    def _evidence_query(self, layer: SupplyChainLayer) -> str:
        seeds = " ".join(layer.seed_giants[:3])
        return f"{layer.name} AI data center supply chain bottleneck {seeds}"


def _bounded_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


def _first_result_url(result: ToolResult) -> str:
    results = result.data.get("results", [])
    if not result.ok or not isinstance(results, list) or not results:
        return ""
    first = results[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("url") or "").strip()
