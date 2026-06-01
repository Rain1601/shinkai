"""Persistence of human decisions on agent-proposed patches.

The harness emits ``memory_patch_proposed`` / ``filter_policy_patch_proposed``
/ ``checklist_patch_proposed`` events as it reflects on a run. Those events
become rows in the Actions inbox; this store remembers what the human did
about each one (accept / reject / modify) so revisiting the inbox does not
lose state.

Section name in ``shinkai_state``: ``action_patches``.
"""

from __future__ import annotations

from time import time
from typing import Literal

from pydantic import BaseModel

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.persistence import default_state_store

PatchDecision = Literal["pending", "accepted", "rejected", "modified"]


class PatchDecisionRecord(BaseModel):
    patch_id: str
    decision: PatchDecision = "pending"
    decided_at: float | None = None
    note: str = ""


class InMemoryActionsStore:
    def __init__(self) -> None:
        self._decisions: dict[str, PatchDecisionRecord] = {}
        self._lock = LoopBoundLock()
        self._loaded = False

    async def get_decision(self, patch_id: str) -> PatchDecisionRecord:
        async with self._lock.get():
            await self._ensure_loaded()
            return self._decisions.get(
                patch_id, PatchDecisionRecord(patch_id=patch_id)
            )

    async def set_decision(
        self,
        patch_id: str,
        decision: PatchDecision,
        note: str = "",
    ) -> PatchDecisionRecord:
        async with self._lock.get():
            await self._ensure_loaded()
            record = PatchDecisionRecord(
                patch_id=patch_id,
                decision=decision,
                decided_at=time(),
                note=note,
            )
            self._decisions[patch_id] = record
            await self._persist()
            return record

    async def list_all(self) -> dict[str, PatchDecisionRecord]:
        async with self._lock.get():
            await self._ensure_loaded()
            return dict(self._decisions)

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_state_store.load()
        payload = state.get("action_patches", {})
        if isinstance(payload, dict):
            self._decisions = {
                pid: PatchDecisionRecord.model_validate(item)
                for pid, item in payload.items()
                if isinstance(item, dict)
            }
        self._loaded = True

    async def _persist(self) -> None:
        await default_state_store.save_section(
            "action_patches",
            {
                pid: record.model_dump(mode="json")
                for pid, record in self._decisions.items()
            },
        )

    def _reset_for_tests(self) -> None:
        self._decisions = {}
        self._loaded = False


default_actions_store = InMemoryActionsStore()
