from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from shinkai_api.api.runs import reasoning_tree
from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor


def test_reasoning_tree_links_hypotheses_to_claims_and_evidence() -> None:
    async def scenario() -> None:
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Reasoning Tree",
                scope={
                    "objective": "validate reasoning tree shape",
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

        tree = await reasoning_tree(run.id)
        assert tree.run_id == run.id
        assert tree.hypotheses, "expected at least one hypothesis"

        seen_evidence_ids: set[str] = set()
        for hyp_node in tree.hypotheses:
            assert hyp_node.hypothesis.hypothesis_id
            assert hyp_node.hypothesis.state in {"active", "falsified", "superseded"}
            assert hyp_node.claims, (
                f"hypothesis {hyp_node.hypothesis.hypothesis_id} has no claims"
            )
            for resolved in hyp_node.claims:
                assert resolved.claim.hypothesis_id == hyp_node.hypothesis.hypothesis_id
                total = len(resolved.supporting_evidence) + len(
                    resolved.contradicting_evidence
                )
                assert total > 0, resolved.claim.claim_id
                for evidence in resolved.supporting_evidence:
                    assert evidence.source_id in tree.sources
                    seen_evidence_ids.add(evidence.evidence_id)
                for evidence in resolved.contradicting_evidence:
                    assert evidence.source_id in tree.sources
                    seen_evidence_ids.add(evidence.evidence_id)
        assert seen_evidence_ids, "no evidence resolved through any claim"

    asyncio.run(scenario())


def test_reasoning_tree_raises_404_when_run_missing() -> None:
    async def scenario() -> None:
        with pytest.raises(HTTPException) as exc:
            await reasoning_tree("does-not-exist")
        assert exc.value.status_code == 404

    asyncio.run(scenario())
