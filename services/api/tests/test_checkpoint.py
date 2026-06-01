from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor
from shinkai_api.schemas.events import AgentEvent


def test_harness_pauses_and_resumes_at_checkpoint() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Checkpoint Loop",
                scope={
                    "objective": "validate checkpoint pause and release",
                    "allow_live_sources": False,
                    "checkpoints_enabled": True,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        await default_run_executor.start(run.id)

        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "awaiting_checkpoint":
                break
            if current.status == "completed":
                raise AssertionError(
                    "run completed before raising any checkpoint: "
                    + str([event.type for event in current.events])
                )
            await asyncio.sleep(0.05)

        paused = await default_run_store.get(run.id)
        assert paused.status == "awaiting_checkpoint"
        checkpoint_events = [
            event for event in paused.events if event.type == "checkpoint_raised"
        ]
        assert len(checkpoint_events) == 1
        assert checkpoint_events[0].data["reason"] == "first_dossier_publication"
        dossier_count_at_pause = sum(
            1 for event in paused.events if event.type == "company_dossier_created"
        )
        assert dossier_count_at_pause == 0

        await default_run_store.append_event(
            run.id,
            AgentEvent(
                type="checkpoint_released",
                run_id=run.id,
                data={"source": "test_harness", "decision": "approve", "note": ""},
            ),
        )
        await default_run_store.set_status(run.id, "running", "running")

        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        finished = await default_run_store.get(run.id)
        assert finished.status == "completed"
        dossier_count_after = sum(
            1 for event in finished.events if event.type == "company_dossier_created"
        )
        assert dossier_count_after > 0

    asyncio.run(scenario())


def test_checkpoints_disabled_by_default() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="No Checkpoint",
                scope={
                    "objective": "no checkpoints when not opted in",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "completed"
        checkpoint_events = [
            event for event in current.events if event.type == "checkpoint_raised"
        ]
        assert checkpoint_events == []

    asyncio.run(scenario())
