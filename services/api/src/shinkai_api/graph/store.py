from __future__ import annotations

import uuid

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.graph.models import Graph, GraphDelta, Node
from shinkai_api.persistence import default_json_state
from shinkai_api.runs.models import Run


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._graphs_by_run: dict[str, Graph] = {}
        self._lock = LoopBoundLock()
        self._loaded = False

    async def create_for_run(self, run: Run) -> Graph:
        async with self._lock.get():
            await self._ensure_loaded()
            graph = Graph(
                graph_id=uuid.uuid4().hex[:12],
                run_id=run.id,
                mode=run.mode,
                nodes=[
                    Node(
                        id=f"anchor_{run.id}",
                        type="Entity",
                        confidence=1.0,
                        label=run.anchor,
                        data={"name": run.anchor, "role": "anchor"},
                        tags=["anchor"],
                    )
                ],
            )
            self._graphs_by_run[run.id] = graph
            await self._persist()
            return graph

    async def get_by_run(self, run_id: str) -> Graph:
        async with self._lock.get():
            await self._ensure_loaded()
            return self._graphs_by_run[run_id]

    async def apply_delta(self, run_id: str, delta: GraphDelta) -> Graph:
        async with self._lock.get():
            await self._ensure_loaded()
            graph = self._graphs_by_run[run_id]
            existing_nodes = {node.id for node in graph.nodes}
            existing_edges = {edge.id for edge in graph.edges}
            graph.nodes.extend(node for node in delta.nodes if node.id not in existing_nodes)
            graph.edges.extend(edge for edge in delta.edges if edge.id not in existing_edges)
            await self._persist()
            return graph

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_json_state.load()
        graphs = state.get("graphs_by_run", {})
        if isinstance(graphs, dict):
            self._graphs_by_run = {
                run_id: Graph.model_validate(payload)
                for run_id, payload in graphs.items()
                if isinstance(payload, dict)
            }
        self._loaded = True

    async def _persist(self) -> None:
        await default_json_state.save_section(
            "graphs_by_run",
            {
                run_id: graph.model_dump(mode="json")
                for run_id, graph in self._graphs_by_run.items()
            },
        )


def node_id(prefix: str, value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return f"{prefix}_{safe[:48]}_{uuid.uuid4().hex[:6]}"


def edge_id(from_node: str, relation: str, to_node: str) -> str:
    return f"e_{from_node[:16]}_{relation}_{to_node[:16]}_{uuid.uuid4().hex[:6]}"


default_graph_store = InMemoryGraphStore()
