from __future__ import annotations

import asyncio

from shinkai_api.agent import ShinkaiHarness
from shinkai_api.eval import build_eval_report
from shinkai_api.graph import default_graph_store
from shinkai_api.research import default_research_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.tools import ToolResult, default_tool_registry
from shinkai_api.tools.base import Tool


class FakeWebSearchTool(Tool):
    name = "web_search"
    description = "Fake deterministic web search for tests."

    async def run(self, **kwargs):
        query = str(kwargs.get("query") or "")
        return ToolResult(
            ok=True,
            summary=f"Found fake source for {query}",
            data={
                "query": query,
                "results": [
                    {
                        "title": "Fake AI infrastructure source",
                        "url": "https://www.sec.gov/Archives/fake-ai-infrastructure",
                        "snippet": (
                            "Power and packaging are constraints for AI data center "
                            "supply chains."
                        ),
                    },
                    {
                        "title": "Fake AI infrastructure source two",
                        "url": "https://example.org/ai-infrastructure",
                        "snippet": (
                            "AI clusters add pressure to power, packaging, and optical "
                            "networking suppliers."
                        ),
                    }
                ],
            },
        )


class FakeWebExtractTool(Tool):
    name = "web_extract"
    description = "Fake deterministic web extract for tests."

    async def run(self, **kwargs):
        url = str(kwargs.get("url") or "")
        return ToolResult(
            ok=True,
            summary="Fake source page",
            data={
                "url": url,
                "title": "Fake source page",
                "excerpt": (
                    "AI data center buildouts require power equipment, advanced "
                    "packaging, optical networking, and liquid cooling suppliers."
                ),
            },
        )


class FakeContradictionWebSearchTool(Tool):
    name = "web_search"
    description = "Fake source search that returns refuting evidence for refute queries."

    async def run(self, **kwargs):
        query = str(kwargs.get("query") or "")
        if "refute" in query or "not a bottleneck" in query:
            return ToolResult(
                ok=True,
                summary=f"Found fake refuting source for {query}",
                data={
                    "query": query,
                    "results": [
                        {
                            "title": "Fake company IR refutes bottleneck exposure",
                            "url": "https://investor.example.com/ai-capacity",
                            "snippet": (
                                "Management says power equipment is not a bottleneck "
                                "and there is no supply constraint."
                            ),
                        }
                    ],
                },
            )
        return ToolResult(
            ok=True,
            summary=f"Found fake source for {query}",
            data={
                "query": query,
                "results": [
                    {
                        "title": "Fake SEC source",
                        "url": "https://www.sec.gov/Archives/fake-ai-infrastructure",
                        "snippet": (
                            "Power and packaging are constraints for AI data center "
                            "supply chains."
                        ),
                    },
                    {
                        "title": "Fake secondary source",
                        "url": "https://example.org/ai-infrastructure",
                        "snippet": "AI clusters add pressure to power and packaging suppliers.",
                    },
                ],
            },
        )


def test_autonomous_harness_generates_trace_and_graph() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Autonomous Discovery",
                scope={
                    "objective": "discover AI supply-chain key companies",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 80},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        run.graph_id = graph.graph_id

        async for event in ShinkaiHarness().run(run):
            await default_run_store.append_event(run.id, event)

        graph = await default_graph_store.get_by_run(run.id)
        event_types = [event.type for event in run.events]

        assert event_types[-1] == "done"
        assert event_types.count("supply_chain_layer_started") >= 4
        assert event_types.count("candidate_scored") >= 12
        assert event_types.count("claim_validated") >= 4
        assert event_types.count("company_deep_analysis_completed") >= 12
        assert "review_completed" in event_types
        assert "optimization_decision" in event_types
        assert "memory_patch_proposed" in event_types
        assert "filter_policy_patch_proposed" in event_types
        assert "checklist_patch_proposed" in event_types
        assert len(graph.nodes) >= 53
        assert len(graph.edges) >= 56
        assert any(node.type == "Claim" for node in graph.nodes)
        assert any(node.type == "Evidence" for node in graph.nodes)
        assert any(node.type == "Question" for node in graph.nodes)
        assert any(node.type == "Thesis" for node in graph.nodes)
        report = build_eval_report(run, graph)
        assert report.process_score is not None
        assert report.discovery_score is not None
        assert report.evidence_score == 0.0

    asyncio.run(scenario())


def test_autonomous_harness_records_refuting_evidence() -> None:
    async def scenario() -> None:
        default_tool_registry.register(FakeContradictionWebSearchTool())
        default_tool_registry.register(FakeWebExtractTool())
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Autonomous Discovery",
                scope={
                    "objective": "discover AI supply-chain key companies",
                    "allow_live_sources": True,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 20},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        run.graph_id = graph.graph_id

        async for event in ShinkaiHarness().run(run):
            await default_run_store.append_event(run.id, event)

        claim_events = [event for event in run.events if event.type == "claim_validated"]
        research_state = await default_research_store.get_run_state(run.id)

        assert claim_events
        assert all(event.data["verification"] == "refute" for event in claim_events)
        assert all(event.data["contradicting_evidence_ids"] for event in claim_events)
        assert any(claim.verification == "refute" for claim in research_state.claims)
        assert any(
            evidence.metadata.get("polarity") == "contradict"
            for evidence in research_state.evidence
        )

    asyncio.run(scenario())


def test_autonomous_harness_can_use_source_backed_evidence() -> None:
    async def scenario() -> None:
        default_tool_registry.register(FakeWebSearchTool())
        default_tool_registry.register(FakeWebExtractTool())
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Autonomous Discovery",
                scope={
                    "objective": "discover AI supply-chain key companies",
                    "allow_live_sources": True,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 20},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        run.graph_id = graph.graph_id

        async for event in ShinkaiHarness().run(run):
            await default_run_store.append_event(run.id, event)

        graph = await default_graph_store.get_by_run(run.id)
        evidence_events = [event for event in run.events if event.type == "evidence_found"]
        claim_events = [event for event in run.events if event.type == "claim_validated"]
        company_events = [
            event for event in run.events if event.type == "company_deep_analysis_completed"
        ]
        research_state = await default_research_store.get_run_state(run.id)
        assert evidence_events
        assert all(event.data["source_backed"] for event in evidence_events)
        assert claim_events
        assert all(event.data["status"] == "supported" for event in claim_events)
        assert company_events
        assert research_state.sources
        assert research_state.evidence
        assert research_state.claims
        assert research_state.candidates
        assert research_state.tasks
        assert any(
            event.type == "tool_result" and event.data["name"] == "web_extract"
            for event in run.events
        )
        assert any("source-backed" in node.tags for node in graph.nodes)
        assert any("extracted" in node.tags for node in graph.nodes)
        assert any("candidate-claim" in node.tags for node in graph.nodes)
        assert any("mode-a-queue" in node.tags for node in graph.nodes)
        assert any(
            event.type == "review_completed" and event.data["review_score"] >= 0.78
            for event in run.events
        )
        report = build_eval_report(run, graph)
        assert report.evidence_score == 1.0
        assert report.process_score is not None
        assert report.reasoning_score is not None

    asyncio.run(scenario())
