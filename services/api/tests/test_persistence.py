from __future__ import annotations

import asyncio

from shinkai_api.core.config import settings
from shinkai_api.graph import GraphDelta, Node
from shinkai_api.graph.store import InMemoryGraphStore
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
