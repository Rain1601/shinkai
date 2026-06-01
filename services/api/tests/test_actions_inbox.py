from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from shinkai_api.api.actions import (
    PatchDecideRequest,
    decide_patch,
    get_critics,
    get_memory,
    get_triggers,
    list_patches,
)
from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_triggers_endpoint_returns_all_five() -> None:
    async def scenario() -> None:
        triggers = await get_triggers()
        keys = {trigger.key for trigger in triggers}
        assert keys == {
            "discovery_mode",
            "allow_live_sources",
            "checkpoints_enabled",
            "critics_enabled",
            "force_llm_planner",
        }

    asyncio.run(scenario())


def test_critics_endpoint_returns_three_personas() -> None:
    async def scenario() -> None:
        critics = await get_critics()
        keys = [critic.key for critic in critics]
        assert keys == ["buffett", "short_seller", "auditor"]
        for critic in critics:
            assert critic.prompt_text
            assert critic.v0_rule_summary_en
            assert critic.v0_rule_summary_zh

    asyncio.run(scenario())


def test_patch_inbox_after_run_then_decide_accept() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Actions Inbox",
                scope={
                    "objective": "validate actions inbox",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 80},
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

        # The harness emits at least one patch per layer.
        pending = await list_patches(status="pending")
        assert len(pending) >= 1
        first = pending[0]
        assert first.decision == "pending"
        assert first.run_id == run.id

        decided = await decide_patch(
            first.patch_id, PatchDecideRequest(decision="accept", note="ok")
        )
        assert decided.decision == "accepted"
        assert decided.decided_at is not None
        assert decided.note == "ok"

        # Inbox no longer surfaces it under pending.
        pending_after = await list_patches(status="pending")
        assert first.patch_id not in {p.patch_id for p in pending_after}

        accepted = await list_patches(status="accepted")
        assert first.patch_id in {p.patch_id for p in accepted}

        # Memory layers reflect the new procedural memory entry.
        layers = await get_memory()
        proc = next(layer for layer in layers if layer.layer == "procedural")
        assert proc.count >= 1

    asyncio.run(scenario())


def test_decide_unknown_patch_returns_404() -> None:
    async def scenario() -> None:
        with pytest.raises(HTTPException) as exc:
            await decide_patch(
                "does-not-exist", PatchDecideRequest(decision="accept")
            )
        assert exc.value.status_code == 404

    asyncio.run(scenario())
