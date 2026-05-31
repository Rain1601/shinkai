from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import RunExecutor, default_run_executor
from shinkai_api.schemas.events import AgentEvent
from shinkai_api.tools import default_tool_registry
from shinkai_api.tools.base import Tool, ToolResult


class _StubWebSearchTool(Tool):
    name = "web_search"
    description = "Stub web search; never fires HTTP."

    async def run(self, **kwargs):
        return ToolResult(
            ok=True,
            summary="stub",
            data={"query": kwargs.get("query"), "results": []},
        )


class _StubWebExtractTool(Tool):
    name = "web_extract"
    description = "Stub web extract; never fires HTTP."

    async def run(self, **kwargs):
        return ToolResult(
            ok=True,
            summary="stub",
            data={"url": kwargs.get("url"), "title": "stub", "excerpt": ""},
        )


def test_run_store_deduplicates_events_by_id() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Idempotency",
                scope={"allow_live_sources": False},
            )
        )
        event = AgentEvent(event_id="fixed_event", type="plan", run_id=run.id)

        await default_run_store.append_event(run.id, event)
        await default_run_store.append_event(run.id, event)

        current = await default_run_store.get(run.id)
        assert [item.event_id for item in current.events].count("fixed_event") == 1

    asyncio.run(scenario())


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

        for _ in range(600):
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

        for _ in range(600):
            parent = await default_run_store.get(run.id)
            if parent.child_run_ids:
                break
            await asyncio.sleep(0.05)

        parent = await default_run_store.get(run.id)
        assert len(parent.child_run_ids) == 1
        child_id = parent.child_run_ids[0]

        for _ in range(600):
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


def test_run_executor_recovers_running_run() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Recoverable Run",
                scope={
                    "objective": "recover after restart",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 20},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)
        await default_run_store.set_status(run.id, "running", "planning")

        executor = RunExecutor()
        recovered = await executor.recover_active_runs()

        assert [item.id for item in recovered] == [run.id]
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        event_types = [event.type for event in current.events]
        assert "run_recovered" in event_types
        assert current.status == "completed"

    asyncio.run(scenario())


def test_recovery_does_not_duplicate_events_or_nodes() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Idempotent Recovery",
                scope={
                    "objective": "verify recovery idempotency",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 80},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)

        await default_run_executor.start(run.id)
        for _ in range(1200):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        baseline_run = await default_run_store.get(run.id)
        baseline_graph = await default_graph_store.get_by_run(run.id)
        baseline_event_count = len(baseline_run.events)
        baseline_node_count = len(baseline_graph.nodes)
        baseline_edge_count = len(baseline_graph.edges)
        baseline_child_run_created = sum(
            1 for event in baseline_run.events if event.type == "child_run_created"
        )

        await default_run_store.set_status(run.id, "running", "recovering")
        executor = RunExecutor()
        await executor.recover_active_runs()
        for _ in range(1200):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        recovered_run = await default_run_store.get(run.id)
        recovered_graph = await default_graph_store.get_by_run(run.id)
        recovered_child_run_created = sum(
            1 for event in recovered_run.events if event.type == "child_run_created"
        )

        assert len(recovered_graph.nodes) == baseline_node_count
        assert len(recovered_graph.edges) == baseline_edge_count
        assert recovered_child_run_created == baseline_child_run_created
        assert len(recovered_run.events) <= baseline_event_count + 2

    asyncio.run(scenario())


def test_run_executor_stops_when_tool_call_budget_is_exhausted() -> None:
    async def scenario() -> None:
        default_tool_registry.register(_StubWebSearchTool())
        default_tool_registry.register(_StubWebExtractTool())
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Budget Guard",
                scope={
                    "objective": "stop before tool calls",
                    "allow_live_sources": True,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 0},
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
        event_types = [event.type for event in current.events]
        assert "budget_exhausted" in event_types
        assert "tool_result" not in event_types
        assert current.lifecycle_stage == "budget_exhausted"

    asyncio.run(scenario())
