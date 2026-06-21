"""Analysis write tools — Bottleneck / KeyDataPoint / InvestmentThesis.

These are shinkai's alpha — they capture not just the supply chain but the
*risks*, *quantitative facts*, and *recommendations* derived from research.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shinkai_api.tools.base import ToolResult

from ..schemas import (
    bottleneck_id as make_bottleneck_id,
)
from ..schemas import (
    key_data_id as make_key_data_id,
)
from ..schemas import (
    relation_id as make_relation_id,
)
from ..schemas import (
    thesis_id as make_thesis_id,
)
from ._base import PROVENANCE_SCHEMA, IndustryGraphTool


class AddBottleneckTool(IndustryGraphTool):
    name = "add_bottleneck"
    description = "Register a bottleneck / risk and auto-create affects relations."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["capacity", "geopolitical", "technology", "demand", "regulation"],
            },
            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
            "description": {"type": "string"},
            "affects": {"type": "array", "items": {"type": "string"}},
            "at_layer": {"type": ["string", "null"]},
            "at_company": {"type": ["string", "null"]},
            "expected_resolution": {"type": ["string", "null"]},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["slug", "type", "severity", "description", "affects", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        bid = make_bottleneck_id(kwargs["slug"])
        now = datetime.now(UTC).isoformat()
        attrs = {
            "type": kwargs["type"],
            "severity": kwargs["severity"],
            "status": "active",
            "affects": list(kwargs.get("affects") or []),
            "at_layer": kwargs.get("at_layer"),
            "at_company": kwargs.get("at_company"),
            "expected_resolution": kwargs.get("expected_resolution"),
        }
        entity_result = await self.store.upsert_entity(
            {
                "id": bid,
                "kind": "Bottleneck",
                "labels": [kwargs["slug"]],
                "description": kwargs["description"],
                "attributes": attrs,
                "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                "created_at": now,
                "updated_at": now,
            },
            source_ref_id=source_ref_id,
        )
        # `affects` relations: bottleneck → company
        created_rels: list[str] = []
        for affected_id in kwargs.get("affects") or []:
            rid = make_relation_id("affects", bid, affected_id)
            await self.store.upsert_relation(
                {
                    "id": rid,
                    "type": "affects",
                    "source_id": bid,
                    "target_id": affected_id,
                    "weights": [],
                    "attributes": {},
                    "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                    "created_at": now,
                    "updated_at": now,
                },
                source_ref_id=source_ref_id,
            )
            created_rels.append(rid)
        # bottleneck_at relation if at_layer / at_company supplied
        anchor = kwargs.get("at_layer") or kwargs.get("at_company")
        if anchor:
            rid = make_relation_id("bottleneck_at", bid, anchor)
            await self.store.upsert_relation(
                {
                    "id": rid,
                    "type": "bottleneck_at",
                    "source_id": bid,
                    "target_id": anchor,
                    "weights": [],
                    "attributes": {},
                    "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                    "created_at": now,
                    "updated_at": now,
                },
                source_ref_id=source_ref_id,
            )
            created_rels.append(rid)
        return self._ok(
            f"Bottleneck {entity_result['action']}: {bid} (+{len(created_rels)} relations)",
            {"bottleneck_id": bid, "relation_ids": created_rels, **entity_result},
        )


class UpdateBottleneckTool(IndustryGraphTool):
    name = "update_bottleneck"
    description = "Update severity / status / description of an existing bottleneck."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "bottleneck_id": {"type": "string"},
            "severity": {"type": ["string", "null"]},
            "status": {
                "type": ["string", "null"],
                "enum": ["active", "resolved", "monitoring", None],
            },
            "description": {"type": ["string", "null"]},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["bottleneck_id", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        bid = kwargs["bottleneck_id"]
        existing = self.store.index.get_entity(bid)
        if existing is None:
            return self._err(f"No bottleneck {bid}")
        new_attrs = dict(existing.get("attributes") or {})
        if kwargs.get("severity"):
            new_attrs["severity"] = kwargs["severity"]
        if kwargs.get("status"):
            new_attrs["status"] = kwargs["status"]
        result = await self.store.upsert_entity(
            {
                **existing,
                "attributes": new_attrs,
                "description": kwargs.get("description") or existing.get("description"),
            },
            source_ref_id=source_ref_id,
        )
        return self._ok(f"Bottleneck updated: {bid}", result)


class AddKeyDataTool(IndustryGraphTool):
    name = "add_key_data"
    description = "Register a quantitative fact about a subject."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "subject_id": {"type": "string"},
            "metric": {"type": "string"},
            "value": {"type": "string"},
            "value_numeric": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]},
            "period": {"type": "string"},
            "slug": {"type": ["string", "null"]},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["subject_id", "metric", "value", "period", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        slug = kwargs.get("slug") or f"{kwargs['subject_id']}_{kwargs['metric']}_{kwargs['period']}"
        kdp = make_key_data_id(slug)
        now = datetime.now(UTC).isoformat()
        attrs = {
            "subject_id": kwargs["subject_id"],
            "metric": kwargs["metric"],
            "value": kwargs["value"],
            "value_numeric": kwargs.get("value_numeric"),
            "unit": kwargs.get("unit"),
            "period": kwargs["period"],
        }
        entity_result = await self.store.upsert_entity(
            {
                "id": kdp,
                "kind": "KeyDataPoint",
                "labels": [kwargs["metric"]],
                "description": f"{kwargs['metric']} = {kwargs['value']} ({kwargs['period']})",
                "attributes": attrs,
                "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                "created_at": now,
                "updated_at": now,
            },
            source_ref_id=source_ref_id,
        )
        # key_data_about edge: KDP → subject
        rid = make_relation_id("key_data_about", kdp, kwargs["subject_id"])
        await self.store.upsert_relation(
            {
                "id": rid,
                "type": "key_data_about",
                "source_id": kdp,
                "target_id": kwargs["subject_id"],
                "weights": [],
                "attributes": {},
                "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                "created_at": now,
                "updated_at": now,
            },
            source_ref_id=source_ref_id,
        )
        return self._ok(
            f"KeyDataPoint {entity_result['action']}: {kdp}",
            {"key_data_id": kdp, "relation_id": rid, **entity_result},
        )


class AddInvestmentThesisTool(IndustryGraphTool):
    name = "add_investment_thesis"
    description = "Register an investment thesis and auto-create watched_in relations."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "target_id": {"type": "string"},
            "slug": {"type": "string"},
            "stocks_to_watch": {
                "type": "array",
                "description": "Each entry: {ticker, rationale, pt?, conviction?}",
                "items": {"type": "object"},
            },
            "bias": {
                "type": "string",
                "enum": ["bullish", "constructive", "cautious", "bearish"],
            },
            "horizon": {"type": "string", "enum": ["short", "medium", "long"]},
            "rationale": {"type": "string"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": [
            "target_id",
            "slug",
            "stocks_to_watch",
            "bias",
            "horizon",
            "rationale",
            "source_ref",
        ],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        thesis = make_thesis_id(kwargs["slug"])
        now = datetime.now(UTC).isoformat()
        attrs = {
            "target_id": kwargs["target_id"],
            "stocks_to_watch": kwargs["stocks_to_watch"],
            "bias": kwargs["bias"],
            "horizon": kwargs["horizon"],
        }
        entity_result = await self.store.upsert_entity(
            {
                "id": thesis,
                "kind": "InvestmentThesis",
                "labels": [kwargs["slug"]],
                "description": kwargs["rationale"],
                "attributes": attrs,
                "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                "created_at": now,
                "updated_at": now,
            },
            source_ref_id=source_ref_id,
        )
        # watched_in: thesis → each ticker company id
        created: list[str] = []
        for s in kwargs["stocks_to_watch"]:
            ticker = s.get("ticker")
            if not ticker:
                continue
            company_id = f"co:{ticker}"
            rid = make_relation_id("watched_in", thesis, company_id)
            await self.store.upsert_relation(
                {
                    "id": rid,
                    "type": "watched_in",
                    "source_id": thesis,
                    "target_id": company_id,
                    "weights": [],
                    "attributes": {
                        "rationale": s.get("rationale"),
                        "pt": s.get("pt"),
                    },
                    "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
                    "created_at": now,
                    "updated_at": now,
                },
                source_ref_id=source_ref_id,
            )
            created.append(rid)
        return self._ok(
            f"Thesis {entity_result['action']}: {thesis} (+{len(created)} watched_in)",
            {"thesis_id": thesis, "watched_relation_ids": created, **entity_result},
        )


__all__ = [
    "AddBottleneckTool",
    "AddInvestmentThesisTool",
    "AddKeyDataTool",
    "UpdateBottleneckTool",
]
