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


def test_constraint_intent_appends_filter_policy_patch() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Constraint Inject",
                scope={
                    "objective": "validate constraint intent",
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
            data={"intent": "constraint", "note": "ignore POWL sources"},
        )
        await default_run_store.append_event(run.id, injection)

        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        ack = next(
            event for event in current.events if event.type == "injection_acknowledged"
        )
        assert ack.data["applied_to"] == "filter"
        assert ack.data["adopted"] is True
        assert ack.data["filter_policy_patches_count"] >= 1

    asyncio.run(scenario())


def test_correction_intent_penalizes_hypothesis_confidence() -> None:
    from shinkai_api.research import default_research_store

    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Correction Inject",
                scope={
                    "objective": "validate correction intent",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        await default_run_executor.start(run.id)

        # Wait for at least one hypothesis to exist, then inject correction.
        for _ in range(600):
            hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
            if hypotheses:
                break
            await asyncio.sleep(0.05)
        assert hypotheses, "expected at least one hypothesis before injection"

        await default_run_store.append_event(
            run.id,
            AgentEvent(
                type="human_injection",
                run_id=run.id,
                data={"intent": "correction", "note": "your judgment is too optimistic"},
            ),
        )

        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        ack = next(
            event for event in current.events if event.type == "injection_acknowledged"
        )
        assert ack.data["applied_to"] == "hypothesis"
        assert ack.data["delta"] < 0
        # Find the hypothesis_confidence_updated event tied to this correction.
        human_correction_events = [
            event
            for event in current.events
            if event.type == "hypothesis_confidence_updated"
            and event.data.get("kind") == "human_correction"
        ]
        assert len(human_correction_events) == 1

    asyncio.run(scenario())


def test_guidance_intent_records_without_state_change() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Guidance Inject",
                scope={
                    "objective": "validate guidance intent",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)
        await default_run_store.append_event(
            run.id,
            AgentEvent(
                type="human_injection",
                run_id=run.id,
                data={"intent": "guidance", "note": "consider catalysts beyond 12 months"},
            ),
        )
        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        ack = next(
            event for event in current.events if event.type == "injection_acknowledged"
        )
        assert ack.data["applied_to"] == "none"
        assert ack.data["adopted"] is False

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
