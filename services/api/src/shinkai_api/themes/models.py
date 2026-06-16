from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

EdgeKind = Literal["prerequisite", "adjacent", "downstream", "shares_entity"]
GraphGenerator = Literal[
    "deepseek_llm",
    "deterministic_fallback",
    "fallback_after_reject",
    "empty",
]


class ThemeCluster(BaseModel):
    cluster_id: str
    cluster_name: str
    rationale: str = ""
    theme_ids: list[str] = Field(default_factory=list)


class ThemeEdge(BaseModel):
    from_theme_id: str
    to_theme_id: str
    kind: EdgeKind = "adjacent"
    weight: float = 0.5
    reason: str = ""


class ThemeGraph(BaseModel):
    generated_at: float = Field(default_factory=time.time)
    generator: GraphGenerator = "empty"
    clusters: list[ThemeCluster] = Field(default_factory=list)
    edges: list[ThemeEdge] = Field(default_factory=list)
    unclustered_theme_ids: list[str] = Field(default_factory=list)
    reject_reason: str | None = None


def empty_graph() -> ThemeGraph:
    return ThemeGraph(generator="empty")
