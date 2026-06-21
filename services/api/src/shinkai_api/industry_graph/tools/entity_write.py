"""Entity write tools. All but ``register_source`` require ``source_ref``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shinkai_api.tools.base import ToolResult

from ..schemas import source_id as make_source_id
from ._base import PROVENANCE_SCHEMA, IndustryGraphTool


class RegisterSourceTool(IndustryGraphTool):
    name = "register_source"
    description = "Register a research report. Idempotent on slug. Returns source_id."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "publisher": {"type": "string"},
            "title": {"type": "string"},
            "date": {"type": "string"},
            "url": {"type": ["string", "null"]},
            "pages": {"type": ["array", "null"], "items": {"type": "integer"}},
            "tickers": {"type": ["array", "null"], "items": {"type": "string"}},
            "asset_class": {"type": ["string", "null"]},
            "slug_hint": {"type": ["string", "null"]},
        },
        "required": ["publisher", "title", "date"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        publisher = kwargs.get("publisher")
        title = kwargs.get("title")
        date = kwargs.get("date")
        if not (publisher and title and date):
            return self._err("publisher/title/date are required.")
        slug_hint = kwargs.get("slug_hint") or f"{publisher} {date} {title}"
        sid = make_source_id(slug_hint)
        attrs = {
            "publisher": publisher,
            "title": title,
            "date": date,
            "url": kwargs.get("url"),
            "pages_relevant": kwargs.get("pages") or [],
            "tickers": kwargs.get("tickers") or [],
            "asset_class": kwargs.get("asset_class"),
        }
        now = datetime.now(UTC).isoformat()
        result = await self.store.upsert_entity(
            {
                "id": sid,
                "kind": "Source",
                "labels": [title],
                "description": f"{publisher} · {date}",
                "attributes": attrs,
                "created_at": now,
                "updated_at": now,
            },
            source_ref_id=None,  # Source itself is self-attributed
        )
        return self._ok(
            f"Source {result['action']}: {sid}", {"source_id": sid, **result}
        )


class UpsertEntityTool(IndustryGraphTool):
    name = "upsert_entity"
    description = "Insert or merge an entity. Returns the resolved entity + diff."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "aliases": {"type": ["array", "null"], "items": {"type": "string"}},
            "description": {"type": ["string", "null"]},
            "facets": {"type": "object"},
            "attributes": {"type": "object"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["id", "kind", "labels", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        now = datetime.now(UTC).isoformat()
        record = {
            "id": kwargs["id"],
            "kind": kwargs["kind"],
            "labels": kwargs.get("labels") or [],
            "aliases": kwargs.get("aliases") or [],
            "description": kwargs.get("description"),
            "facets": kwargs.get("facets") or {},
            "attributes": kwargs.get("attributes") or {},
            "provenance": [
                {**kwargs["source_ref"], "asserted_at": now},
            ],
            "created_at": now,
            "updated_at": now,
        }
        result = await self.store.upsert_entity(record, source_ref_id=source_ref_id)
        return self._ok(f"Entity {result['action']}: {kwargs['id']}", result)


class SetAttributeTool(IndustryGraphTool):
    name = "set_attribute"
    description = "Set a single attribute on an entity."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "key": {"type": "string"},
            "value": {},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["entity_id", "key", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        entity_id = kwargs["entity_id"]
        existing = self.store.index.get_entity(entity_id)
        if existing is None:
            return self._err(f"No entity {entity_id}")
        new_attrs = dict(existing.get("attributes") or {})
        new_attrs[kwargs["key"]] = kwargs.get("value")
        result = await self.store.upsert_entity(
            {**existing, "attributes": new_attrs},
            source_ref_id=source_ref_id,
        )
        return self._ok(f"Attribute set: {entity_id}.{kwargs['key']}", result)


class AddAliasTool(IndustryGraphTool):
    name = "add_alias"
    description = "Append an alias (ticker / alternate name) to an existing entity."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "alias": {"type": "string"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["entity_id", "alias", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        entity_id = kwargs["entity_id"]
        existing = self.store.index.get_entity(entity_id)
        if existing is None:
            return self._err(f"No entity {entity_id}")
        aliases = list(existing.get("aliases") or [])
        if kwargs["alias"] not in aliases:
            aliases.append(kwargs["alias"])
        result = await self.store.upsert_entity(
            {**existing, "aliases": aliases},
            source_ref_id=source_ref_id,
        )
        return self._ok(f"Alias added: {entity_id} <- {kwargs['alias']}", result)


class AddFacetValueTool(IndustryGraphTool):
    name = "add_facet_value"
    description = "Append a value to a multi-valued facet axis (e.g. headquartered_in: TW)."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "facet_name": {"type": "string"},
            "value": {"type": "string"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["entity_id", "facet_name", "value", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        entity_id = kwargs["entity_id"]
        existing = self.store.index.get_entity(entity_id)
        if existing is None:
            return self._err(f"No entity {entity_id}")
        facets = dict(existing.get("facets") or {})
        axis = kwargs["facet_name"]
        current = list(facets.get(axis) or [])
        if kwargs["value"] not in current:
            current.append(kwargs["value"])
        facets[axis] = current
        result = await self.store.upsert_entity(
            {**existing, "facets": facets},
            source_ref_id=source_ref_id,
        )
        return self._ok(
            f"Facet {axis}+={kwargs['value']} on {entity_id}",
            result,
        )


class DeprecateEntityTool(IndustryGraphTool):
    name = "deprecate_entity"
    description = "Mark an entity as deprecated (soft-delete) with a reason."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "reason": {"type": "string"},
            "source_ref": PROVENANCE_SCHEMA,
        },
        "required": ["entity_id", "reason", "source_ref"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        source_ref_id, err = self._require_source_ref(kwargs)
        if err:
            return self._err(err)
        result = await self.store.deprecate_entity(
            kwargs["entity_id"],
            reason=kwargs["reason"],
            source_ref_id=source_ref_id,
        )
        return self._ok(f"Entity {result['action']}: {kwargs['entity_id']}", result)


__all__ = [
    "AddAliasTool",
    "AddFacetValueTool",
    "DeprecateEntityTool",
    "RegisterSourceTool",
    "SetAttributeTool",
    "UpsertEntityTool",
]
