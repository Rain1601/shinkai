from __future__ import annotations

import asyncio

from shinkai_api.graph import default_graph_store
from shinkai_api.research import default_research_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_hypothesis_created_per_layer_with_confidence_history() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Hypothesis Lifecycle",
                scope={
                    "objective": "validate hypothesis events",
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

        current = await default_run_store.get(run.id)
        assert current.status == "completed"

        created_events = [
            event for event in current.events if event.type == "hypothesis_created"
        ]
        confidence_events = [
            event for event in current.events if event.type == "hypothesis_confidence_updated"
        ]
        assert len(created_events) >= 4, [event.type for event in current.events[:20]]
        assert len(confidence_events) >= 4

        for event in created_events:
            assert event.data["hypothesis_id"]
            assert event.data["claim"]
            assert event.data["initial_confidence"] == 0.5
            assert event.data["falsification_condition"]

        for event in confidence_events:
            assert event.data["method"] == "evidence_weighted_average_v0"
            assert event.data["kind"] in {"support", "contradict"}
            assert 0.0 <= event.data["new_confidence"] <= 1.0

        hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
        assert len(hypotheses) >= 4
        for hypothesis in hypotheses:
            assert hypothesis.state == "active"
            assert hypothesis.confidence_history, hypothesis.hypothesis_id
            assert hypothesis.confidence == hypothesis.confidence_history[-1].confidence
            assert all(0.0 <= point.confidence <= 1.0 for point in hypothesis.confidence_history)

    asyncio.run(scenario())
