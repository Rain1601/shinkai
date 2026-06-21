"""Query tools — pure reads against the in-memory index."""

from __future__ import annotations

from typing import Any

from shinkai_api.tools.base import ToolResult

from ._base import IndustryGraphTool


class FindEntityTool(IndustryGraphTool):
    name = "find_entity"
    description = "Search entities by free-text query / kind / facets."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": ["string", "null"]},
            "kind": {"type": ["string", "null"]},
            "facets": {
                "type": "object",
                "description": "axis -> value, e.g. {\"sectors\": \"Semiconductor\"}",
            },
            "limit": {"type": "integer", "default": 20},
        },
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = (kwargs.get("query") or "").lower()
        kind = kwargs.get("kind")
        facets = kwargs.get("facets") or {}
        limit = int(kwargs.get("limit") or 20)
        candidates = list(self.store.index.by_id.values())
        if kind:
            candidates = [c for c in candidates if c.get("kind") == kind]
        for axis, value in facets.items():
            candidates = [
                c
                for c in candidates
                if value in (c.get("facets", {}).get(axis) or [])
                or value == c.get("facets", {}).get(axis)
            ]
        if query:
            def _matches(c: dict[str, Any]) -> bool:
                haystack = " ".join(
                    [
                        c.get("id", ""),
                        *(c.get("labels") or []),
                        *(c.get("aliases") or []),
                        c.get("description") or "",
                    ]
                ).lower()
                return query in haystack

            candidates = [c for c in candidates if _matches(c)]
        candidates = candidates[:limit]
        return self._ok(
            f"Found {len(candidates)} entities.",
            {"entities": candidates},
        )


class GetEntityTool(IndustryGraphTool):
    name = "get_entity"
    description = "Fetch one entity by ID along with its incident relations."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        eid = kwargs.get("id")
        if not eid:
            return self._err("`id` is required.")
        entity = self.store.index.get_entity(eid)
        if entity is None:
            return self._err(f"No entity {eid}")
        rels = self.store.index.relations_for(eid, direction="both")
        return self._ok(
            f"Entity {eid} ({entity.get('kind')}) with {len(rels)} incident relations.",
            {"entity": entity, "relations": rels},
        )


class FindRelationsTool(IndustryGraphTool):
    name = "find_relations"
    description = "Filter relations by source / target / type / period."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "source_id": {"type": ["string", "null"]},
            "target_id": {"type": ["string", "null"]},
            "type": {"type": ["string", "null"]},
            "period": {"type": ["string", "null"]},
        },
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_id = kwargs.get("source_id")
        target_id = kwargs.get("target_id")
        rtype = kwargs.get("type")
        period = kwargs.get("period")
        relations = list(self.store.index.relations_by_id.values())
        if source_id:
            relations = [r for r in relations if r["source_id"] == source_id]
        if target_id:
            relations = [r for r in relations if r["target_id"] == target_id]
        if rtype:
            relations = [r for r in relations if r["type"] == rtype]
        if period:
            relations = [
                r
                for r in relations
                if any(w.get("period") == period for w in (r.get("weights") or []))
            ]
        return self._ok(
            f"Found {len(relations)} relations.", {"relations": relations}
        )


class WalkPathTool(IndustryGraphTool):
    name = "walk_path"
    description = "All simple paths between two entities up to max_depth."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_id": {"type": "string"},
            "to_id": {"type": "string"},
            "max_depth": {"type": "integer", "default": 4},
            "edge_types": {"type": ["array", "null"], "items": {"type": "string"}},
        },
        "required": ["from_id", "to_id"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        from_id = kwargs.get("from_id")
        to_id = kwargs.get("to_id")
        if not from_id or not to_id:
            return self._err("`from_id` and `to_id` are required.")
        paths = self.store.index.walk_paths(
            from_id,
            to_id,
            max_depth=int(kwargs.get("max_depth") or 4),
            edge_types=kwargs.get("edge_types"),
        )
        return self._ok(f"Found {len(paths)} paths.", {"paths": paths})


class FindBottlenecksTool(IndustryGraphTool):
    name = "find_bottlenecks"
    description = (
        "List Bottleneck entities, optionally affecting an anchor "
        "or filtered by severity."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "anchor_id": {"type": ["string", "null"]},
            "type": {"type": ["string", "null"]},
            "severity_min": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "medium",
            },
        },
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        anchor_id = kwargs.get("anchor_id")
        btype = kwargs.get("type")
        severity_order = {"low": 0, "medium": 1, "high": 2}
        sev_min = severity_order[kwargs.get("severity_min") or "medium"]
        candidates = self.store.index.list_by_kind("Bottleneck")
        out = []
        for c in candidates:
            attrs = c.get("attributes") or {}
            if btype and attrs.get("type") != btype:
                continue
            if severity_order.get(attrs.get("severity") or "low", 0) < sev_min:
                continue
            if anchor_id:
                affects = attrs.get("affects") or []
                if anchor_id not in affects:
                    continue
            out.append(c)
        return self._ok(f"Found {len(out)} bottlenecks.", {"bottlenecks": out})


class FindKeyDataTool(IndustryGraphTool):
    name = "find_key_data"
    description = "Quantitative facts about a subject, filtered by metric substring or period."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "subject_id": {"type": "string"},
            "metric_substr": {"type": ["string", "null"]},
            "period": {"type": ["string", "null"]},
        },
        "required": ["subject_id"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        subject_id = kwargs.get("subject_id")
        if not subject_id:
            return self._err("`subject_id` is required.")
        metric_substr = (kwargs.get("metric_substr") or "").lower()
        period = kwargs.get("period")
        candidates = self.store.index.list_by_kind("KeyDataPoint")
        out = []
        for c in candidates:
            attrs = c.get("attributes") or {}
            if attrs.get("subject_id") != subject_id:
                continue
            if metric_substr and metric_substr not in (attrs.get("metric") or "").lower():
                continue
            if period and attrs.get("period") != period:
                continue
            out.append(c)
        return self._ok(f"Found {len(out)} key data points.", {"key_data": out})


class SearchSourcesTool(IndustryGraphTool):
    name = "search_sources"
    description = "Find Source entities (research reports) by publisher / ticker / date range."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "publisher": {"type": ["string", "null"]},
            "ticker": {"type": ["string", "null"]},
            "date_from": {"type": ["string", "null"]},
            "date_to": {"type": ["string", "null"]},
        },
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        publisher = kwargs.get("publisher")
        ticker = kwargs.get("ticker")
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        sources = self.store.index.list_by_kind("Source")
        out = []
        for s in sources:
            attrs = s.get("attributes") or {}
            if publisher and attrs.get("publisher") != publisher:
                continue
            if ticker:
                tickers = attrs.get("tickers") or []
                if ticker not in tickers:
                    continue
            d = attrs.get("date")
            if date_from and (d or "") < date_from:
                continue
            if date_to and (d or "") > date_to:
                continue
            out.append(s)
        return self._ok(f"Found {len(out)} sources.", {"sources": out})


class ListFacetValuesTool(IndustryGraphTool):
    name = "list_facet_values"
    description = "Enumerate values currently observed in a facet axis (for dropdowns / context)."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"facet_name": {"type": "string"}},
        "required": ["facet_name"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        facet_name = kwargs.get("facet_name")
        if not facet_name:
            return self._err("`facet_name` is required.")
        values: set[str] = set()
        for (axis, value) in self.store.index.by_facet:
            if axis == facet_name:
                values.add(value)
        return self._ok(
            f"{len(values)} known values for facet {facet_name}.",
            {"facet_name": facet_name, "values": sorted(values)},
        )


class FulltextSearchTool(IndustryGraphTool):
    name = "fulltext_search"
    description = (
        "Full-text search across descriptions and quotes. "
        "V0 stub falls back to find_entity scan."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        # V0.5 will swap to a Whoosh index. For now do the same scan as
        # FindEntityTool but include provenance quotes in the haystack.
        query = (kwargs.get("query") or "").lower()
        if not query:
            return self._err("`query` is required.")
        limit = int(kwargs.get("limit") or 20)
        out = []
        for c in self.store.index.by_id.values():
            hay = " ".join(
                [
                    c.get("description") or "",
                    *(c.get("labels") or []),
                    *(p.get("quote") or "" for p in (c.get("provenance") or [])),
                ]
            ).lower()
            if query in hay:
                out.append(c)
                if len(out) >= limit:
                    break
        return self._ok(f"Found {len(out)} matches.", {"entities": out})


__all__ = [
    "FindBottlenecksTool",
    "FindEntityTool",
    "FindKeyDataTool",
    "FindRelationsTool",
    "FulltextSearchTool",
    "GetEntityTool",
    "ListFacetValuesTool",
    "SearchSourcesTool",
    "WalkPathTool",
]
