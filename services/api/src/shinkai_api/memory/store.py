from __future__ import annotations

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.memory.models import (
    EpisodicRecord,
    MemoryEntry,
    MemoryLayer,
    ProceduralRecord,
    SemanticFact,
    WorkingMemoryItem,
)


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._entries: dict[MemoryLayer, dict[str, MemoryEntry]] = {
            "working": {},
            "episodic": {},
            "semantic": {},
            "procedural": {},
        }
        self._lock = LoopBoundLock()

    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        async with self._lock.get():
            self._entries[entry.layer][entry.entry_id] = entry
            return entry

    async def list(self, layer: MemoryLayer, *, run_id: str | None = None) -> list[MemoryEntry]:
        async with self._lock.get():
            entries = list(self._entries[layer].values())
        if run_id is None:
            return entries
        return [entry for entry in entries if entry.run_id == run_id]

    async def get(self, layer: MemoryLayer, entry_id: str) -> MemoryEntry | None:
        async with self._lock.get():
            return self._entries[layer].get(entry_id)

    async def consolidate_working_to_episodic(
        self,
        run_id: str,
        episodic_id: str,
        *,
        anchor: str,
        outcome: str,
        eval_score: float | None = None,
        min_confidence: float = 0.6,
    ) -> EpisodicRecord:
        """Promote per-run working items above a confidence threshold into a single episode.

        This is the simplest consolidation policy; a real implementation would have
        the critic decide which items earn a slot.
        """
        async with self._lock.get():
            working_items = [
                entry
                for entry in self._entries["working"].values()
                if entry.run_id == run_id and entry.confidence >= min_confidence
            ]
            summary_text = (
                f"Run {run_id} ({anchor}): {outcome}. "
                f"Consolidated {len(working_items)} working-memory items."
            )
            record = EpisodicRecord(
                entry_id=episodic_id,
                run_id=run_id,
                anchor=anchor,
                outcome=outcome,
                eval_score=eval_score,
                consolidated_from=[item.entry_id for item in working_items],
                text=summary_text,
                confidence=(
                    sum(item.confidence for item in working_items) / max(1, len(working_items))
                ),
            )
            self._entries["episodic"][episodic_id] = record
            for item in working_items:
                self._entries["working"].pop(item.entry_id, None)
            return record

    async def clear_working_for_run(self, run_id: str) -> int:
        async with self._lock.get():
            to_remove = [
                entry_id
                for entry_id, entry in self._entries["working"].items()
                if entry.run_id == run_id
            ]
            for entry_id in to_remove:
                self._entries["working"].pop(entry_id, None)
            return len(to_remove)

    def _reset_for_tests(self) -> None:
        for layer in self._entries:
            self._entries[layer].clear()


default_memory_store = InMemoryMemoryStore()


# Re-export models so callers don't need to import from two places
__all__ = [
    "EpisodicRecord",
    "InMemoryMemoryStore",
    "MemoryEntry",
    "MemoryLayer",
    "ProceduralRecord",
    "SemanticFact",
    "WorkingMemoryItem",
    "default_memory_store",
]
