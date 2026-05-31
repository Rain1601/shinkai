from __future__ import annotations

import asyncio
from contextlib import suppress

from shinkai_api.agent import ShinkaiHarness
from shinkai_api.graph import default_graph_store
from shinkai_api.runs.models import Run, RunCreate
from shinkai_api.runs.store import default_run_store
from shinkai_api.schemas.events import AgentEvent

TERMINAL_STATUSES = {"completed", "failed", "aborted"}


class RunExecutor:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, run_id: str) -> Run:
        run = await default_run_store.get(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            return run
        if run.status in TERMINAL_STATUSES:
            return run

        run = await default_run_store.set_status(run_id, "running", "scoped")
        self._tasks[run_id] = asyncio.create_task(self._execute(run_id))
        return run

    async def abort(self, run_id: str) -> Run:
        run = await default_run_store.set_status(run_id, "aborted", "aborted")
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return run

    async def _execute(self, run_id: str) -> None:
        harness = ShinkaiHarness()
        try:
            run = await default_run_store.get(run_id)
            async for event in harness.run(run):
                if not await self._wait_until_runnable(run_id):
                    return
                await default_run_store.append_event(run_id, event)
                await self._apply_event_side_effects(run_id, event)
            current = await default_run_store.get(run_id)
            if current.status != "aborted":
                await default_run_store.set_status(run_id, "completed", "completed")
        except asyncio.CancelledError:
            current = await default_run_store.get(run_id)
            if current.status != "aborted":
                await default_run_store.set_status(run_id, "aborted", "aborted")
            raise
        except Exception as exc:  # pragma: no cover - defensive API boundary
            await default_run_store.append_event(
                run_id,
                AgentEvent(
                    type="error",
                    run_id=run_id,
                    data={"message": str(exc), "source": "run_executor"},
                ),
            )
            await default_run_store.set_status(run_id, "failed", "failed")

    async def _wait_until_runnable(self, run_id: str) -> bool:
        while True:
            run = await default_run_store.get(run_id)
            if run.status == "aborted":
                return False
            if run.status != "paused":
                return True
            await asyncio.sleep(0.5)

    async def _apply_event_side_effects(self, run_id: str, event: AgentEvent) -> None:
        stage = _stage_from_event(event)
        if stage:
            await default_run_store.set_lifecycle_stage(run_id, stage)
        if event.type == "usage":
            await default_run_store.add_usage(
                run_id,
                input_tokens=int(event.data.get("input_tokens") or 0),
                output_tokens=int(event.data.get("output_tokens") or 0),
                cost_usd=float(event.data.get("cost_usd") or 0.0),
            )
        if event.type == "eval_completed":
            run = await default_run_store.get(run_id)
            await self._maybe_spawn_next_spiral(run)

    async def _maybe_spawn_next_spiral(self, parent: Run) -> None:
        if parent.child_run_ids or not bool(parent.scope.get("autonomy")):
            return
        spiral_index = _scope_int(parent.scope, "spiral_index", default=1)
        max_spirals = _scope_int(parent.scope, "max_spirals", default=1)
        if spiral_index >= max_spirals:
            return

        next_anchor = _next_spiral_anchor(parent)
        child_scope = {
            **parent.scope,
            "spiral_index": spiral_index + 1,
            "parent_run_id": parent.id,
            "objective": (
                f"Continue autonomous spiral {spiral_index + 1}: validate and deepen "
                f"{next_anchor}"
            ),
        }
        child = await default_run_store.create(
            RunCreate(
                mode=parent.mode,
                anchor=next_anchor,
                scope=child_scope,
                budget=parent.budget,
                parent_run_id=parent.id,
                triggered_by="eval",
                trigger_reason="self_iteration_after_review_optimize",
            )
        )
        graph = await default_graph_store.create_for_run(child)
        child = await default_run_store.set_graph_id(child.id, graph.graph_id)
        await default_run_store.add_child_run(parent.id, child.id)
        await default_run_store.append_event(
            parent.id,
            AgentEvent(
                type="child_run_created",
                run_id=parent.id,
                data={
                    "child_run_id": child.id,
                    "child_anchor": child.anchor,
                    "spiral_index": spiral_index + 1,
                    "max_spirals": max_spirals,
                    "trigger": "eval_completed",
                },
            ),
        )
        await default_run_store.append_event(
            child.id,
            AgentEvent(
                type="run_start",
                run_id=child.id,
                parent_id=parent.id,
                data={
                    "mode": child.mode,
                    "anchor": child.anchor,
                    "triggered_by": child.triggered_by,
                    "trigger_reason": child.trigger_reason,
                },
            ),
        )
        await self.start(child.id)


def _stage_from_event(event: AgentEvent) -> str | None:
    loop_index = event.data.get("loop_index")
    if event.type == "plan":
        return "planning"
    if event.type == "supply_chain_layer_started":
        return f"loop_{loop_index}_expanding" if loop_index else "expanding"
    if event.type == "review_completed":
        return f"loop_{loop_index}_review" if loop_index else "review"
    if event.type == "optimization_decision":
        return f"loop_{loop_index}_optimize" if loop_index else "optimize"
    if event.type == "eval_completed":
        return "evaluating"
    if event.type == "done":
        return "completed"
    if event.type == "error":
        return "failed"
    return None


def _scope_int(scope: dict, key: str, default: int) -> int:
    try:
        return int(scope.get(key) or default)
    except (TypeError, ValueError):
        return default


def _next_spiral_anchor(parent: Run) -> str:
    optimization_events = [
        event for event in parent.events if event.type == "optimization_decision"
    ]
    if optimization_events:
        frontier = optimization_events[-1].data.get("next_frontier")
        if isinstance(frontier, str) and frontier.strip():
            return frontier.strip()[:120]
    return f"{parent.anchor} deeper spiral"


default_run_executor = RunExecutor()
