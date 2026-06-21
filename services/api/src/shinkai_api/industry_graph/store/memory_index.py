"""In-memory indices over the industry graph.

The file store is the durable ground truth. ``IndexLayer`` is a derived view
loaded from those files at startup (and incrementally updated on writes). It
provides O(1) ID / kind / ticker lookups, facet-keyed dicts, and a NetworkX
graph for path / hub queries.

Whoosh full-text index is deferred to V0.5 (spec §13). Stub for now.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx

from ..schemas import EntityBase, RelationBase

EntityRecord = dict[str, Any] | EntityBase
RelationRecord = dict[str, Any] | RelationBase


def _as_dict(record: EntityRecord | RelationRecord) -> dict[str, Any]:
    """Accept either Pydantic models or raw dicts; normalise to dict."""
    if hasattr(record, "model_dump"):
        return record.model_dump()  # type: ignore[union-attr]
    return dict(record)  # type: ignore[arg-type]


class IndexLayer:
    """In-memory indices over entities and relations.

    Build with :meth:`add_entity` / :meth:`add_relation` then query via the
    public dicts and :attr:`graph`. Or call :meth:`bulk_load` to populate from
    parsed shards in one shot.
    """

    def __init__(self) -> None:
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_kind: dict[str, list[str]] = defaultdict(list)
        self.by_facet: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.by_ticker: dict[str, str] = {}

        self.relations_by_id: dict[str, dict[str, Any]] = {}
        self.relations_by_source: dict[str, list[str]] = defaultdict(list)
        self.relations_by_target: dict[str, list[str]] = defaultdict(list)
        self.relations_by_type: dict[str, list[str]] = defaultdict(list)

        # NetworkX multi-directed graph. Node keys are entity ids; edge keys
        # are relation ids. Edge attributes carry the relation type for fast
        # filtered traversal.
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()

    # ---------- mutation ----------
    def add_entity(self, entity: EntityRecord) -> None:
        record = _as_dict(entity)
        eid = record["id"]
        # Replace any previous record under this id.
        self.by_id[eid] = record
        kind = record.get("kind")
        if kind and eid not in self.by_kind[kind]:
            self.by_kind[kind].append(eid)

        # Facets — multi-valued lists of strings under known axes + open extras.
        facets = record.get("facets") or {}
        for axis, value in facets.items():
            if value is None or axis == "concept_level":
                continue
            if isinstance(value, list):
                for v in value:
                    if v not in self.by_facet[(axis, v)]:
                        # idempotent append
                        pass
                    if eid not in self.by_facet[(axis, v)]:
                        self.by_facet[(axis, v)].append(eid)
            elif isinstance(value, str):
                if eid not in self.by_facet[(axis, value)]:
                    self.by_facet[(axis, value)].append(eid)

        # Ticker index — pulled from attributes.ticker if present.
        attrs = record.get("attributes") or {}
        ticker = attrs.get("ticker")
        if ticker:
            self.by_ticker[ticker] = eid

        # NetworkX node.
        self.graph.add_node(eid, kind=kind, label=(record.get("labels") or [eid])[0])

    def add_relation(self, relation: RelationRecord) -> None:
        record = _as_dict(relation)
        rid = record["id"]
        rtype = record["type"]
        s = record["source_id"]
        t = record["target_id"]

        self.relations_by_id[rid] = record
        if rid not in self.relations_by_source[s]:
            self.relations_by_source[s].append(rid)
        if rid not in self.relations_by_target[t]:
            self.relations_by_target[t].append(rid)
        if rid not in self.relations_by_type[rtype]:
            self.relations_by_type[rtype].append(rid)

        # NetworkX edge — key=rid lets us update if the same id appears twice.
        # add_node is idempotent so we don't need to check presence first.
        if s not in self.graph:
            self.graph.add_node(s)
        if t not in self.graph:
            self.graph.add_node(t)
        self.graph.add_edge(s, t, key=rid, type=rtype, relation_id=rid)

    def remove_entity(self, entity_id: str) -> None:
        record = self.by_id.pop(entity_id, None)
        if record is None:
            return
        kind = record.get("kind")
        if kind and entity_id in self.by_kind.get(kind, []):
            self.by_kind[kind].remove(entity_id)
        # Facets: scan; cheap at our scale.
        for key, ids in list(self.by_facet.items()):
            if entity_id in ids:
                ids.remove(entity_id)
                if not ids:
                    del self.by_facet[key]
        # Ticker.
        for ticker, eid in list(self.by_ticker.items()):
            if eid == entity_id:
                del self.by_ticker[ticker]
        # Graph (drops incident edges automatically).
        if entity_id in self.graph:
            self.graph.remove_node(entity_id)

    def remove_relation(self, relation_id: str) -> None:
        record = self.relations_by_id.pop(relation_id, None)
        if record is None:
            return
        s = record["source_id"]
        t = record["target_id"]
        rtype = record["type"]
        for bucket in (
            self.relations_by_source[s],
            self.relations_by_target[t],
            self.relations_by_type[rtype],
        ):
            if relation_id in bucket:
                bucket.remove(relation_id)
        # Drop graph edge with that key.
        if self.graph.has_edge(s, t, key=relation_id):
            self.graph.remove_edge(s, t, key=relation_id)

    def bulk_load(
        self,
        *,
        entities: list[EntityRecord] | None = None,
        relations: list[RelationRecord] | None = None,
    ) -> None:
        for e in entities or []:
            self.add_entity(e)
        for r in relations or []:
            self.add_relation(r)

    # ---------- query helpers ----------
    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.by_id.get(entity_id)

    def list_by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [self.by_id[i] for i in self.by_kind.get(kind, [])]

    def list_by_facet(self, axis: str, value: str) -> list[dict[str, Any]]:
        return [self.by_id[i] for i in self.by_facet.get((axis, value), [])]

    def find_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        eid = self.by_ticker.get(ticker)
        return self.by_id.get(eid) if eid else None

    def relations_for(
        self,
        entity_id: str,
        *,
        direction: str = "both",
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List relations touching an entity.

        direction: "out" (entity is source), "in" (entity is target), or "both".
        type: optional relation type filter.
        """
        rids: list[str] = []
        if direction in ("out", "both"):
            rids.extend(self.relations_by_source.get(entity_id, []))
        if direction in ("in", "both"):
            rids.extend(self.relations_by_target.get(entity_id, []))
        # Dedupe while preserving order.
        seen: set[str] = set()
        unique = []
        for rid in rids:
            if rid in seen:
                continue
            seen.add(rid)
            rec = self.relations_by_id[rid]
            if type is not None and rec["type"] != type:
                continue
            unique.append(rec)
        return unique

    def walk_paths(
        self,
        from_id: str,
        to_id: str,
        *,
        max_depth: int = 4,
        edge_types: list[str] | None = None,
    ) -> list[list[str]]:
        """All simple paths up to ``max_depth`` edges. Optional type filter."""
        if from_id not in self.graph or to_id not in self.graph:
            return []
        if edge_types is None:
            return [
                list(p)
                for p in nx.all_simple_paths(
                    self.graph, from_id, to_id, cutoff=max_depth
                )
            ]
        # Build a filtered view limited to allowed edge types.
        allowed = set(edge_types)

        def edge_filter(u: str, v: str, k: Any) -> bool:
            data = self.graph[u][v][k]
            return data.get("type") in allowed

        sub = nx.subgraph_view(self.graph, filter_edge=edge_filter)
        return [
            list(p)
            for p in nx.all_simple_paths(sub, from_id, to_id, cutoff=max_depth)
        ]

    def neighbors(
        self,
        entity_id: str,
        *,
        direction: str = "both",
        edge_types: list[str] | None = None,
    ) -> list[str]:
        """One-hop neighbours of an entity, optionally filtered by edge type."""
        if entity_id not in self.graph:
            return []
        out: set[str] = set()
        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(entity_id, data=True):
                if edge_types is None or data.get("type") in edge_types:
                    out.add(target)
        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(entity_id, data=True):
                if edge_types is None or data.get("type") in edge_types:
                    out.add(source)
        return sorted(out)

    # ---------- stats ----------
    def stats(self) -> dict[str, int]:
        return {
            "entities": len(self.by_id),
            "relations": len(self.relations_by_id),
            "kinds": len(self.by_kind),
            "facets": len(self.by_facet),
            "tickers": len(self.by_ticker),
            "graph_nodes": self.graph.number_of_nodes(),
            "graph_edges": self.graph.number_of_edges(),
        }
