from __future__ import annotations

import asyncio

from shinkai_api.memory import (
    InMemoryMemoryStore,
    ProceduralRecord,
    SemanticFact,
    WorkingMemoryItem,
)


def test_memory_store_layers_are_isolated() -> None:
    async def scenario() -> None:
        store = InMemoryMemoryStore()
        await store.add(
            WorkingMemoryItem(entry_id="w1", run_id="r1", text="scratch", confidence=0.4)
        )
        await store.add(
            SemanticFact(
                entry_id="s1",
                text="NVDA HBM supplier list (verified 2026)",
                subject="NVDA",
                predicate="hbm_supplier",
                object_="SK Hynix",
                confidence=0.9,
            )
        )

        working = await store.list("working")
        semantic = await store.list("semantic")

        assert len(working) == 1
        assert len(semantic) == 1
        assert working[0].entry_id == "w1"

    asyncio.run(scenario())


def test_consolidation_filters_by_confidence_and_moves_items() -> None:
    async def scenario() -> None:
        store = InMemoryMemoryStore()
        await store.add(
            WorkingMemoryItem(entry_id="w1", run_id="r1", text="weak", confidence=0.3)
        )
        await store.add(
            WorkingMemoryItem(entry_id="w2", run_id="r1", text="strong", confidence=0.8)
        )
        await store.add(
            WorkingMemoryItem(entry_id="w3", run_id="other_run", text="other", confidence=0.9)
        )

        episode = await store.consolidate_working_to_episodic(
            "r1",
            "ep1",
            anchor="AI infra",
            outcome="found 3 candidates",
            eval_score=0.72,
        )

        assert episode.consolidated_from == ["w2"]
        assert episode.eval_score == 0.72
        remaining_working = await store.list("working")
        assert {entry.entry_id for entry in remaining_working} == {"w1", "w3"}


    asyncio.run(scenario())


def test_clear_working_for_run() -> None:
    async def scenario() -> None:
        store = InMemoryMemoryStore()
        await store.add(WorkingMemoryItem(entry_id="w1", run_id="r1", text="x", confidence=0.5))
        await store.add(WorkingMemoryItem(entry_id="w2", run_id="r1", text="y", confidence=0.5))
        await store.add(WorkingMemoryItem(entry_id="w3", run_id="r2", text="z", confidence=0.5))

        removed = await store.clear_working_for_run("r1")

        assert removed == 2
        remaining = await store.list("working")
        assert {entry.entry_id for entry in remaining} == {"w3"}

    asyncio.run(scenario())


def test_procedural_record_basic_schema() -> None:
    record = ProceduralRecord(
        entry_id="p1",
        text="For power-infra layer, search SEC 10-Q first.",
        context_signature="layer=power_infra",
        action_sequence=["sec_search", "transcript_fetch", "ir_compare"],
        success_rate=0.62,
    )

    assert record.layer == "procedural"
    assert record.action_sequence == ["sec_search", "transcript_fetch", "ir_compare"]
