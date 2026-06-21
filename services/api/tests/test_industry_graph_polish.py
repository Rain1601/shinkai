"""Polish tests for Tier 1.5: repeat detection, auto source, schema re-validation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shinkai_api.industry_graph import IndustryGraphStore, ToolDispatcher
from shinkai_api.industry_graph.e2e_runner import REPEAT_THRESHOLD


def _store(tmp_path: Path) -> IndustryGraphStore:
    s = IndustryGraphStore(root=tmp_path)
    asyncio.run(s.load())
    return s


# ---- #1 Repeated-call detection ----
def test_repeated_call_returns_hint(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    # Build a deterministic plan that calls the same query tool N+1 times.
    plan = [
        {"tool": "find_entity", "args": {"query": "NVDA", "limit": 5}}
    ] * (REPEAT_THRESHOLD + 1)

    async def run() -> None:
        results = await d.run_calls(plan)
        # The first REPEAT_THRESHOLD calls execute normally;
        # the next one short-circuits.
        executed = [r for r in results if r.get("error") != "repeated_call"]
        warned = [r for r in results if r.get("error") == "repeated_call"]
        assert len(executed) == REPEAT_THRESHOLD
        assert len(warned) == len(plan) - REPEAT_THRESHOLD
        # Hint mentions the offending tool name.
        assert "find_entity" in warned[0]["summary"]
        assert "change strategy" in warned[0]["summary"].lower()

    asyncio.run(run())


def test_varied_args_do_not_trigger_repeat(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    plan = [
        {"tool": "find_entity", "args": {"query": "A"}},
        {"tool": "find_entity", "args": {"query": "B"}},
        {"tool": "find_entity", "args": {"query": "C"}},
        {"tool": "find_entity", "args": {"query": "D"}},
    ]

    async def run() -> None:
        results = await d.run_calls(plan)
        assert all(r["error"] != "repeated_call" for r in results)

    asyncio.run(run())


# ---- #2 Auto register_source on first write ----
def test_auto_register_source_on_first_write(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    # Write call without any source_ref — should still succeed.
    plan = [
        {
            "tool": "upsert_entity",
            "args": {
                "id": "co:NVDA",
                "kind": "Company",
                "labels": ["NVIDIA"],
                # NB: no source_ref
            },
        }
    ]

    async def run() -> None:
        results = await d.run_calls(plan)
        assert results[0]["ok"], results[0]
        # The dispatcher must have produced a synthetic AGENT Source.
        sources = s.index.list_by_kind("Source")
        assert len(sources) == 1
        assert sources[0]["attributes"]["publisher"] == "AGENT"

    asyncio.run(run())


def test_explicit_source_ref_still_wins(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    plan = [
        {
            "tool": "register_source",
            "args": {"publisher": "MS", "title": "Real source", "date": "2026-05-08"},
        },
        {
            "tool": "upsert_entity",
            "args": {
                "id": "co:NVDA",
                "kind": "Company",
                "labels": ["NVIDIA"],
                # source_ref omitted; dispatcher should use MS source, not auto-register.
            },
        },
    ]

    async def run() -> None:
        results = await d.run_calls(plan)
        assert all(r["ok"] for r in results), results
        # Exactly one Source (the MS one); no AGENT source created.
        sources = s.index.list_by_kind("Source")
        assert len(sources) == 1
        assert sources[0]["attributes"]["publisher"] == "MS"

    asyncio.run(run())


# ---- #5 Pydantic re-validation surfaces structured errors ----
def test_unknown_entity_kind_returns_field_level_error(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    plan = [
        {
            "tool": "upsert_entity",
            "args": {
                "id": "co:X",
                "kind": "Quantum",  # not in Literal
                "labels": ["X"],
            },
        }
    ]

    async def run() -> None:
        results = await d.run_calls(plan)
        assert not results[0]["ok"]
        msg = results[0]["summary"]
        assert "kind" in msg.lower()
        # The error should mention SchemaValidationError or similar diagnostic
        assert results[0]["error"] in {"SchemaValidationError", "ValueError"}

    asyncio.run(run())


def test_unknown_relation_type_returns_field_level_error(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = ToolDispatcher(s)
    # Need source + endpoints first
    setup = [
        {
            "tool": "register_source",
            "args": {"publisher": "MS", "title": "X", "date": "2026-05-08"},
        },
        {"tool": "upsert_entity", "args": {"id": "co:A", "kind": "Company", "labels": ["A"]}},
        {"tool": "upsert_entity", "args": {"id": "co:B", "kind": "Company", "labels": ["B"]}},
        {
            "tool": "upsert_relation",
            "args": {
                "type": "bribes",  # not in RelationType Literal
                "source_id": "co:A",
                "target_id": "co:B",
            },
        },
    ]

    async def run() -> None:
        results = await d.run_calls(setup)
        bad = results[-1]
        assert not bad["ok"]
        assert "type" in bad["summary"].lower()

    asyncio.run(run())


def test_repeat_detection_resets_between_dispatchers(tmp_path: Path) -> None:
    """New ToolDispatcher = fresh recent_calls deque."""
    s = _store(tmp_path)
    d1 = ToolDispatcher(s)
    d2 = ToolDispatcher(s)
    plan = [{"tool": "find_entity", "args": {"query": "A"}}] * (REPEAT_THRESHOLD + 1)

    async def run() -> None:
        r1 = await d1.run_calls(plan)
        # d1 should have flagged the tail call.
        assert any(r["error"] == "repeated_call" for r in r1)
        # d2 starts clean; same calls should succeed up to its own threshold.
        r2 = await d2.run_calls(plan)
        executed_in_d2 = [r for r in r2 if r["error"] != "repeated_call"]
        assert len(executed_in_d2) == REPEAT_THRESHOLD

    asyncio.run(run())
