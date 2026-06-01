from __future__ import annotations

import asyncio

from shinkai_api.api.agent import get_agent_summary
from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_agent_summary_after_one_completed_mode_b_run() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Agent Summary",
                scope={
                    "objective": "validate agent summary counters",
                    "allow_live_sources": False,
                    "critics_enabled": True,
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

        summary = await get_agent_summary()

        assert summary.identity.name == "shinkai"
        assert summary.identity.chinese_name == "深海"
        assert summary.identity.tagline_zh
        assert summary.identity.tagline_en

        assert summary.status.status == "idle"
        assert summary.status.last_activity_ts is not None
        assert summary.status.since_first_activity_ts is not None
        assert summary.status.since_first_activity_ts <= summary.status.last_activity_ts

        hr = summary.heartrate
        assert hr.total_runs >= 1
        assert hr.completed_runs >= 1
        assert hr.active_runs == 0
        assert hr.total_hypotheses >= 4
        assert hr.active_hypotheses + hr.falsified_hypotheses <= hr.total_hypotheses
        assert hr.total_dossiers >= 12
        assert hr.total_patches_proposed >= 1
        assert hr.total_critic_verdicts >= 1  # critics_enabled was True

        trigger_keys = {t.key for t in summary.capabilities.triggers}
        assert {
            "discovery_mode",
            "allow_live_sources",
            "checkpoints_enabled",
            "critics_enabled",
            "force_llm_planner",
        } == trigger_keys

    asyncio.run(scenario())


def test_agent_summary_idle_when_no_runs() -> None:
    async def scenario() -> None:
        summary = await get_agent_summary()
        assert summary.status.status == "idle"
        assert summary.heartrate.total_runs == 0
        assert summary.heartrate.total_hypotheses == 0
        assert summary.heartrate.total_dossiers == 0
        assert summary.status.last_activity_ts is None

    asyncio.run(scenario())
