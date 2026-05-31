from __future__ import annotations

from shinkai_api.agent.frontier import FrontierItem, FrontierQueue
from shinkai_api.research import ClaimAssessment


def test_frontier_queue_selects_highest_value_frontier() -> None:
    queue = FrontierQueue(
        [
            FrontierItem(
                frontier_id="frontier_low",
                name="Low",
                priority=0.4,
                confidence=0.6,
                expected_value=0.5,
                estimated_cost=0.6,
            ),
            FrontierItem(
                frontier_id="frontier_high",
                name="High",
                priority=0.8,
                confidence=0.7,
                expected_value=0.8,
                estimated_cost=0.4,
            ),
        ]
    )

    selected = queue.pop_next()

    assert selected is not None
    assert selected.frontier_id == "frontier_high"
    assert selected.status == "running"


def test_frontier_queue_reprioritizes_after_review() -> None:
    item = FrontierItem(
        frontier_id="frontier_power",
        name="Power",
        next_frontier="Switchgear suppliers",
    )
    queue = FrontierQueue([item])
    refute_update = queue.reprioritize_after_review(
        item,
        ClaimAssessment(status="contradicted", verification="refute"),
    )

    assert refute_update["action"] == "block_and_research_contradiction"
    assert item.status == "blocked"

    supported = FrontierItem(
        frontier_id="frontier_packaging",
        name="Packaging",
        next_frontier="Probe cards",
    )
    support_update = queue.reprioritize_after_review(
        supported,
        ClaimAssessment(status="supported", verification="support"),
    )

    assert support_update["action"] == "expand_next_frontier"
    assert support_update["next_frontier"] == "Probe cards"
