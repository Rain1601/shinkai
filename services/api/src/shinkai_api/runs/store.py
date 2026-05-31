from __future__ import annotations

import hashlib
import json
import uuid

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.persistence import default_state_store
from shinkai_api.runs.models import Run, RunCreate
from shinkai_api.schemas.events import AgentEvent


def _event_fingerprint(event: AgentEvent) -> str:
    payload = json.dumps(event.data, sort_keys=True, default=str)
    return hashlib.sha1(f"{event.type}|{payload}".encode()).hexdigest()


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = LoopBoundLock()
        self._loaded = False

    async def create(self, payload: RunCreate) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = Run(
                id=uuid.uuid4().hex[:12],
                mode=payload.mode,
                anchor=payload.anchor,
                parent_run_id=payload.parent_run_id,
                triggered_by=payload.triggered_by,
                trigger_reason=payload.trigger_reason,
                scope=payload.scope,
                budget=payload.budget,
                checklist_ref=(
                    "docs/checklists/value-investing-v1.md"
                    if payload.mode == "mode_a_company"
                    else "docs/checklists/discovery-v1.md"
                ),
            )
            self._runs[run.id] = run
            await self._persist()
            return run

    async def list(self) -> list[Run]:
        async with self._lock.get():
            await self._ensure_loaded()
            return list(self._runs.values())

    async def get(self, run_id: str) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            return self._runs[run_id]

    async def append_event(self, run_id: str, event: AgentEvent) -> None:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[run_id]
            existing_ids = {existing.event_id for existing in run.events}
            if event.event_id in existing_ids:
                return
            fingerprint = _event_fingerprint(event)
            existing_fingerprints = {_event_fingerprint(existing) for existing in run.events}
            if fingerprint in existing_fingerprints:
                return
            run.events.append(event)
            await self._persist()
            await default_state_store.append_event(run_id, event.model_dump(mode="json"))

    async def set_status(self, run_id: str, status: str, lifecycle_stage: str | None = None) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[run_id]
            run.status = status  # type: ignore[assignment]
            if lifecycle_stage is not None:
                run.lifecycle_stage = lifecycle_stage
            await self._persist()
            return run

    async def set_lifecycle_stage(self, run_id: str, lifecycle_stage: str) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[run_id]
            run.lifecycle_stage = lifecycle_stage
            await self._persist()
            return run

    async def set_graph_id(self, run_id: str, graph_id: str) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[run_id]
            run.graph_id = graph_id
            await self._persist()
            return run

    async def add_child_run(self, parent_run_id: str, child_run_id: str) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[parent_run_id]
            if child_run_id not in run.child_run_ids:
                run.child_run_ids.append(child_run_id)
            await self._persist()
            return run

    async def add_usage(
        self,
        run_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> Run:
        async with self._lock.get():
            await self._ensure_loaded()
            run = self._runs[run_id]
            run.usage_summary.input_tokens += input_tokens
            run.usage_summary.output_tokens += output_tokens
            run.usage_summary.cost_usd += cost_usd
            await self._persist()
            return run

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_state_store.load()
        runs = state.get("runs", {})
        if isinstance(runs, dict):
            self._runs = {
                run_id: Run.model_validate(payload)
                for run_id, payload in runs.items()
                if isinstance(payload, dict)
            }
        self._loaded = True

    async def _persist(self) -> None:
        await default_state_store.save_section(
            "runs",
            {
                run_id: run.model_dump(mode="json")
                for run_id, run in self._runs.items()
            },
        )


default_run_store = InMemoryRunStore()
