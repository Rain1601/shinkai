from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor
from shinkai_api.schemas.events import AgentEvent


def test_harness_acknowledges_human_injection() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Injection Loop",
                scope={
                    "objective": "validate injection close-loop",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        injection = AgentEvent(
            type="human_injection",
            run_id=run.id,
            data={"intent": "question", "note": "Why is FORM underwater?"},
        )
        await default_run_store.append_event(run.id, injection)

        await default_run_executor.start(run.id)

        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "completed"
        acks = [event for event in current.events if event.type == "injection_acknowledged"]
        assert len(acks) == 1, [event.type for event in current.events]
        ack = acks[0]
        assert ack.data["injection_id"] == injection.event_id
        assert ack.data["adopted"] is True
        assert ack.data["intent"] == "question"
        assert ack.data["applied_to"] == "frontier"
        assert ack.data["note"] == "Why is FORM underwater?"

    asyncio.run(scenario())


def test_harness_does_not_reacknowledge_after_recovery() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Recovery Idempotency",
                scope={
                    "objective": "do not double-acknowledge",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        injection = AgentEvent(
            type="human_injection",
            run_id=run.id,
            data={"intent": "guidance", "note": "Focus on liquid cooling."},
        )
        await default_run_store.append_event(run.id, injection)

        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        first = await default_run_store.get(run.id)
        first_acks = [event for event in first.events if event.type == "injection_acknowledged"]
        assert len(first_acks) == 1

        # Force a recovery by flipping status back to running and restarting executor.
        await default_run_store.set_status(run.id, "running", "recovering")
        from shinkai_api.runs.executor import RunExecutor

        executor = RunExecutor()
        await executor.recover_active_runs()
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        recovered = await default_run_store.get(run.id)
        recovered_acks = [
            event for event in recovered.events if event.type == "injection_acknowledged"
        ]
        assert len(recovered_acks) == 1

    asyncio.run(scenario())
