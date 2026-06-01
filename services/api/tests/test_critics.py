from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.research import default_research_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_critics_enabled_emits_critiques_and_penalises_reject() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Critics On",
                scope={
                    "objective": "validate L2 critic wiring",
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

        current = await default_run_store.get(run.id)
        assert current.status == "completed"

        dossier_events = [e for e in current.events if e.type == "company_dossier_created"]
        critique_events = [e for e in current.events if e.type == "critic_persona_critique"]
        aggregated_events = [e for e in current.events if e.type == "critic_aggregated"]

        # Three critiques per dossier; one aggregated verdict per dossier.
        assert len(critique_events) == 3 * len(dossier_events)
        assert len(aggregated_events) == len(dossier_events)

        # All three personas are present per dossier.
        personas_per_dossier: dict[str, set[str]] = {}
        for event in critique_events:
            dossier_id = str(event.data["dossier_id"])
            personas_per_dossier.setdefault(dossier_id, set()).add(
                str(event.data["persona"])
            )
        for dossier_id, personas in personas_per_dossier.items():
            assert personas == {"buffett", "short_seller", "auditor"}, (
                f"{dossier_id} only saw {personas}"
            )

        # At least one aggregated reject (deterministic rules produce some).
        rejects = [e for e in aggregated_events if e.data["final"] == "reject"]
        assert rejects, "expected at least one critic_aggregated reject"

        # Each reject produced a hypothesis_confidence_updated with critic_penalty.
        penalty_events = [
            e
            for e in current.events
            if e.type == "hypothesis_confidence_updated"
            and e.data.get("kind") == "critic_penalty"
        ]
        assert len(penalty_events) == len(rejects)

        # Hypothesis confidence in research store reflects penalties.
        hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
        any_critic_in_history = any(
            point.method == "critic_aggregated_v0"
            for hypothesis in hypotheses
            for point in hypothesis.confidence_history
        )
        assert any_critic_in_history

    asyncio.run(scenario())


def test_critics_disabled_by_default() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Critics Off",
                scope={
                    "objective": "default critic gating",
                    "allow_live_sources": False,
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 60},
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
        assert current.status == "completed"
        assert all(e.type != "critic_persona_critique" for e in current.events)
        assert all(e.type != "critic_aggregated" for e in current.events)

    asyncio.run(scenario())
