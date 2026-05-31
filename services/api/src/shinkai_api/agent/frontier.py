from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from shinkai_api.research import ClaimAssessment

FrontierStatus = Literal["queued", "running", "completed", "blocked", "reprioritized"]


class FrontierItem(BaseModel):
    frontier_id: str
    name: str
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    expected_value: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_cost: float = Field(default=0.5, ge=0.01, le=1.0)
    reason: str = ""
    source: str = "planner"
    next_frontier: str = ""
    parent_frontier_id: str | None = None
    status: FrontierStatus = "queued"

    @property
    def selection_score(self) -> float:
        return round(
            (self.priority * 0.45 + self.expected_value * 0.35 + self.confidence * 0.2)
            / max(self.estimated_cost, 0.01),
            3,
        )


class FrontierQueue:
    def __init__(self, items: list[FrontierItem] | None = None) -> None:
        self._items = items or []
        self._completed: list[FrontierItem] = []

    def push(self, item: FrontierItem) -> None:
        if not any(existing.frontier_id == item.frontier_id for existing in self._items):
            self._items.append(item)

    def pop_next(self) -> FrontierItem | None:
        queued = [item for item in self._items if item.status == "queued"]
        if not queued:
            return None
        selected = max(queued, key=lambda item: item.selection_score)
        selected.status = "running"
        return selected

    def complete(self, item: FrontierItem) -> None:
        item.status = "completed"
        self._completed.append(item)

    def reprioritize_after_review(
        self,
        item: FrontierItem,
        assessment: ClaimAssessment,
    ) -> dict:
        if assessment.verification == "support":
            update = {
                "action": "expand_next_frontier",
                "priority_delta": 0.08,
                "reason": "claim supported; deepen adjacent frontier",
                "next_frontier": item.next_frontier,
            }
        elif assessment.verification == "refute":
            update = {
                "action": "block_and_research_contradiction",
                "priority_delta": 0.2,
                "reason": "refuting evidence found; validate contradiction before promotion",
                "next_frontier": f"Resolve contradiction for {item.name}",
            }
            item.status = "blocked"
        elif assessment.verification == "stale":
            update = {
                "action": "refresh_sources",
                "priority_delta": 0.16,
                "reason": "supporting sources are stale; fetch current primary evidence",
                "next_frontier": f"Refresh primary sources for {item.name}",
            }
            item.status = "reprioritized"
        else:
            update = {
                "action": "raise_primary_source_priority",
                "priority_delta": 0.12,
                "reason": "evidence is insufficient; prioritize primary-source search",
                "next_frontier": f"Find primary sources for {item.name}",
            }
            item.status = "reprioritized"
        return {
            **update,
            "frontier_id": item.frontier_id,
            "frontier": item.name,
            "verification": assessment.verification,
            "remaining_queue_size": self.queued_count,
        }

    @property
    def queued_count(self) -> int:
        return sum(1 for item in self._items if item.status == "queued")

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    def snapshot(self) -> list[dict]:
        return [
            {
                **item.model_dump(),
                "selection_score": item.selection_score,
            }
            for item in sorted(self._items, key=lambda item: item.selection_score, reverse=True)
        ]
