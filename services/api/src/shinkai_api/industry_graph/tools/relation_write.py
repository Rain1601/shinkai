"""Relation write tools — all require ``source_ref``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shinkai_api.tools.base import ToolResult

from ..schemas import relation_id as make_relation_id
from ._base import PROVENANCE_SCHEMA, IndustryGraphTool


class UpsertRelationTool(IndustryGraphTool):
    name = "upsert_relation"
    description = "Insert or merge a relation. Dedupe on (type, source, target, period)."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "source_id": {"type": "string"},
            "target_id": {"type": "string"},
            "weights": {
                "type": ["object", "null"],
                "description": "One WeightCell. Optional but recommended.",
                "properties": {
                    "period": {"type": "string"},
                    "values": {"type": "object"},
                },
            },
            "attributes": {"type": "object"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["type", "source_id", "target_id", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        rtype = kwargs["type"]
        src = kwargs["source_id"]
        tgt = kwargs["target_id"]
        weight = kwargs.get("weights")
        period = (weight or {}).get("period")
        rid = make_relation_id(rtype, src, tgt, period)
        now = datetime.now(UTC).isoformat()
        record = {
            "id": rid,
            "type": rtype,
            "source_id": src,
            "target_id": tgt,
            "weights": [weight] if weight else [],
            "attributes": kwargs.get("attributes") or {},
            "provenance": [{**kwargs["source_ref"], "asserted_at": now}],
            "created_at": now,
            "updated_at": now,
        }
        result = await self.store.upsert_relation(record, source_ref_id=source_ref_id)
        return self._ok(f"Relation {result['action']}: {rid}", result)


class AddWeightObservationTool(IndustryGraphTool):
    name = "add_weight_observation"
    description = "Append a new period's WeightCell to an existing relation's time series."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "relation_id": {"type": "string"},
            "weight": {
                "type": "object",
                "properties": {
                    "period": {"type": "string"},
                    "values": {"type": "object"},
                },
                "required": ["period", "values"],
            },
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["relation_id", "weight", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        rid = kwargs["relation_id"]
        existing = self.store.index.relations_by_id.get(rid)
        if existing is None:
            return self._err(f"No relation {rid}")
        merged = {**existing, "weights": [kwargs["weight"]]}
        result = await self.store.upsert_relation(merged, source_ref_id=source_ref_id)
        return self._ok(
            f"Weight observation added for {kwargs['weight'].get('period')}: {rid}",
            result,
        )


class DeprecateRelationTool(IndustryGraphTool):
    name = "deprecate_relation"
    description = "Soft-delete a relation with a stated reason."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "relation_id": {"type": "string"},
            "reason": {"type": "string"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["relation_id", "reason", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        result = await self.store.deprecate_relation(
            kwargs["relation_id"],
            reason=kwargs["reason"],
            source_ref_id=source_ref_id,
        )
        return self._ok(f"Relation {result['action']}: {kwargs['relation_id']}", result)


__all__ = [
    "AddWeightObservationTool",
    "DeprecateRelationTool",
    "UpsertRelationTool",
]
