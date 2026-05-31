from __future__ import annotations

import asyncio

from shinkai_api.core.config import settings
from shinkai_api.graph import GraphDelta, Node
from shinkai_api.graph.store import InMemoryGraphStore
from shinkai_api.research import CandidateCompany, Claim, Evidence, ResearchTask, SourceRef
from shinkai_api.research.store import InMemoryResearchStore
from shinkai_api.runs import RunCreate
from shinkai_api.runs.store import InMemoryRunStore
from shinkai_api.schemas.events import AgentEvent


def test_json_state_recovers_runs_events_and_graph(tmp_path) -> None:
    async def scenario() -> None:
        previous_enabled = settings.persistence_enabled
        previous_path = settings.state_path
        settings.persistence_enabled = True
        settings.state_path = str(tmp_path / "state.json")
        try:
            run_store = InMemoryRunStore()
            graph_store = InMemoryGraphStore()
            run = await run_store.create(
                RunCreate(
                    mode="mode_b_narrative",
                    anchor="Persistence Smoke",
                    scope={"allow_live_sources": False},
                )
            )
            graph = await graph_store.create_for_run(run)
            run = await run_store.set_graph_id(run.id, graph.graph_id)
            await run_store.append_event(run.id, AgentEvent(type="plan", run_id=run.id))
            await run_store.set_status(run.id, "completed", "completed")
            await graph_store.apply_delta(
                run.id,
                GraphDelta(
                    nodes=[
                        Node(
                            id="claim_persisted",
                            type="Claim",
                            label="Persisted claim",
                            confidence=0.8,
                        )
                    ]
                ),
            )

            reloaded_run_store = InMemoryRunStore()
            reloaded_graph_store = InMemoryGraphStore()
            reloaded_run = await reloaded_run_store.get(run.id)
            reloaded_graph = await reloaded_graph_store.get_by_run(run.id)

            assert reloaded_run.status == "completed"
            assert reloaded_run.lifecycle_stage == "completed"
            assert reloaded_run.graph_id == graph.graph_id
            assert reloaded_run.events[0].type == "plan"
            assert any(node.id == "claim_persisted" for node in reloaded_graph.nodes)
        finally:
            settings.persistence_enabled = previous_enabled
            settings.state_path = previous_path

    asyncio.run(scenario())


def test_json_state_recovers_research_domain_models(tmp_path) -> None:
    async def scenario() -> None:
        previous_enabled = settings.persistence_enabled
        previous_path = settings.state_path
        previous_database_url = settings.database_url
        settings.persistence_enabled = True
        settings.state_path = str(tmp_path / "research-state.json")
        settings.database_url = None
        try:
            research_store = InMemoryResearchStore()
            await research_store.upsert_source(
                SourceRef(
                    source_id="src_power",
                    type="web",
                    url="https://example.com/power",
                    title="Power source",
                    metadata={"run_id": "run_1"},
                )
            )
            await research_store.upsert_evidence(
                Evidence(
                    evidence_id="ev_power",
                    source_id="src_power",
                    run_id="run_1",
                    text="Power equipment is a bottleneck.",
                    supports_claim_ids=["claim_power"],
                )
            )
            await research_store.upsert_claim(
                Claim(
                    claim_id="claim_power",
                    run_id="run_1",
                    text="Power equipment is a bottleneck.",
                    evidence_ids=["ev_power"],
                    status="weak",
                )
            )
            await research_store.upsert_candidate(
                CandidateCompany(
                    candidate_id="cand_vrt",
                    run_id="run_1",
                    ticker="VRT",
                    name="Vertiv",
                    claim_ids=["claim_power"],
                    evidence_ids=["ev_power"],
                )
            )
            await research_store.upsert_task(
                ResearchTask(
                    task_id="task_vrt",
                    run_id="run_1",
                    title="Deepen Vertiv",
                    objective="Validate power bottleneck exposure.",
                    candidate_ids=["cand_vrt"],
                )
            )

            reloaded = InMemoryResearchStore()
            state = await reloaded.get_run_state("run_1")

            assert [source.source_id for source in state.sources] == ["src_power"]
            assert [evidence.evidence_id for evidence in state.evidence] == ["ev_power"]
            assert [claim.status for claim in state.claims] == ["weak"]
            assert [candidate.ticker for candidate in state.candidates] == ["VRT"]
            assert [task.task_id for task in state.tasks] == ["task_vrt"]
        finally:
            settings.persistence_enabled = previous_enabled
            settings.state_path = previous_path
            settings.database_url = previous_database_url

    asyncio.run(scenario())
