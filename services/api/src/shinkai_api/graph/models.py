from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NodeType = Literal["Entity", "Claim", "Evidence", "Question", "Thesis"]
EdgeType = Literal["structural", "evidential", "logical", "temporal"]


class Node(BaseModel):
    id: str
    type: NodeType
    confidence: float = 0.0
    label: str = ""
    source_refs: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class Edge(BaseModel):
    id: str
    type: EdgeType
    relation: str
    from_node: str
    to_node: str
    confidence: float = 0.0
    source_refs: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class Graph(BaseModel):
    graph_id: str
    run_id: str
    mode: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class GraphDelta(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    summary: str = ""
