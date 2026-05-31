from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_run_executor_runs_harness_in_background() -> None:
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

        started = await default_run_executor.start(run.id)
        assert started.status == "running"

        for _ in range(100):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "completed"
        assert current.lifecycle_stage == "completed"
        assert current.events[-1].type == "done"
        assert len({event.event_id for event in current.events}) == len(current.events)

    asyncio.run(scenario())


def test_run_executor_spawns_bounded_child_spiral() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Autonomous Discovery",
                scope={
                    "autonomy": True,
                    "max_spirals": 2,
                    "spiral_index": 1,
                    "objective": "discover AI supply-chain key companies",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 20},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        await default_run_executor.start(run.id)

        for _ in range(100):
            parent = await default_run_store.get(run.id)
            if parent.child_run_ids:
                break
            await asyncio.sleep(0.05)

        parent = await default_run_store.get(run.id)
        assert len(parent.child_run_ids) == 1
        child_id = parent.child_run_ids[0]

        for _ in range(100):
            child = await default_run_store.get(child_id)
            if child.status == "completed":
                break
            await asyncio.sleep(0.05)

        parent = await default_run_store.get(run.id)
        child = await default_run_store.get(child_id)
        parent_event_types = [event.type for event in parent.events]
        assert "child_run_created" in parent_event_types
        assert parent_event_types.index("child_run_created") < parent_event_types.index("done")
        assert parent.status == "completed"
        assert child.status == "completed"
        assert child.parent_run_id == run.id
        assert child.triggered_by == "eval"
        assert child.scope["spiral_index"] == 2
        assert child.child_run_ids == []

    asyncio.run(scenario())
