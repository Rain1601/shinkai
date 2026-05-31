from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from shinkai_api.persistence.json_state import _empty_state


@dataclass(frozen=True)
class NormalizedRecord:
    table: str
    key: tuple[str, ...]
    run_id: str | None
    payload: dict[str, Any]


class PostgresStateFile:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def load(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._load_sync)

    async def save_section(self, section: str, value: Any) -> None:
        await asyncio.to_thread(self._save_section_sync, section, value)

    async def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        await asyncio.to_thread(self._append_event_sync, run_id, event)

    async def query_events_by_type(
        self,
        event_type: str,
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._query_events_by_type_sync, event_type, run_id, limit)

    def _query_events_by_type_sync(
        self,
        event_type: str,
        run_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(1000, limit))
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.commit()
            with connection.cursor() as cursor:
                if run_id is None:
                    cursor.execute(
                        """
                        select event_id, run_id, type, ts, payload
                        from shinkai_events
                        where type = %s
                        order by ts desc nulls last
                        limit %s
                        """,
                        (event_type, bounded_limit),
                    )
                else:
                    cursor.execute(
                        """
                        select event_id, run_id, type, ts, payload
                        from shinkai_events
                        where type = %s and run_id = %s
                        order by ts desc nulls last
                        limit %s
                        """,
                        (event_type, run_id, bounded_limit),
                    )
                rows = cursor.fetchall()
            connection.commit()
        return [
            {
                "event_id": str(event_id),
                "run_id": run_id_value,
                "type": event_type,
                "ts": ts,
                "payload": _parse_payload(payload),
            }
            for event_id, run_id_value, event_type, ts, payload in rows
        ]

    def _append_event_sync(self, run_id: str, event: dict[str, Any]) -> None:
        event_id = event.get("event_id")
        if not event_id:
            return
        with self._connect() as connection:
            self._ensure_schema(connection)
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into shinkai_events(event_id, run_id, type, ts, payload, updated_at)
                        values (%s, %s, %s, %s, %s::jsonb, now())
                        on conflict (event_id) do nothing
                        """,
                        (
                            str(event_id),
                            run_id,
                            str(event.get("type") or ""),
                            event.get("ts"),
                            json.dumps(event, ensure_ascii=False),
                        ),
                    )

    def _load_sync(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("select section, payload from shinkai_state")
                rows = cursor.fetchall()
            connection.commit()
        state = _empty_state()
        for section, payload in rows:
            state[str(section)] = _parse_payload(payload)
        return state

    def _save_section_sync(self, section: str, value: Any) -> None:
        with self._connect() as connection:
            self._ensure_schema(connection)
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into shinkai_state(section, payload, updated_at)
                        values (%s, %s::jsonb, now())
                        on conflict (section) do update set
                            payload = excluded.payload,
                            updated_at = excluded.updated_at
                        """,
                        (section, json.dumps(value, ensure_ascii=False)),
                    )
                    self._save_normalized_section(cursor, section, value)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, autocommit=False)

    def _ensure_schema(self, connection) -> None:
        with connection.cursor() as cursor:
            for statement in _schema_statements():
                cursor.execute(statement)

    def _save_normalized_section(self, cursor, section: str, value: Any) -> None:
        for record in normalized_records_for_section(section, value):
            payload_json = json.dumps(record.payload, ensure_ascii=False)
            if record.table == "shinkai_runs":
                cursor.execute(
                    """
                    insert into shinkai_runs(
                        run_id, status, mode, anchor, graph_id, lifecycle_stage, payload, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    on conflict (run_id) do update set
                        status = excluded.status,
                        mode = excluded.mode,
                        anchor = excluded.anchor,
                        graph_id = excluded.graph_id,
                        lifecycle_stage = excluded.lifecycle_stage,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.key[0],
                        str(record.payload.get("status") or ""),
                        str(record.payload.get("mode") or ""),
                        str(record.payload.get("anchor") or ""),
                        record.payload.get("graph_id"),
                        str(record.payload.get("lifecycle_stage") or ""),
                        payload_json,
                    ),
                )
            elif record.table == "shinkai_events":
                cursor.execute(
                    """
                    insert into shinkai_events(event_id, run_id, type, ts, payload, updated_at)
                    values (%s, %s, %s, %s, %s::jsonb, now())
                    on conflict (event_id) do update set
                        run_id = excluded.run_id,
                        type = excluded.type,
                        ts = excluded.ts,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.key[0],
                        record.run_id,
                        str(record.payload.get("type") or ""),
                        record.payload.get("ts"),
                        payload_json,
                    ),
                )
            elif record.table == "shinkai_graph_nodes":
                cursor.execute(
                    """
                    insert into shinkai_graph_nodes(
                        graph_id, node_id, run_id, type, label, confidence, payload, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    on conflict (graph_id, node_id) do update set
                        run_id = excluded.run_id,
                        type = excluded.type,
                        label = excluded.label,
                        confidence = excluded.confidence,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.key[0],
                        record.key[1],
                        record.run_id,
                        str(record.payload.get("type") or ""),
                        str(record.payload.get("label") or ""),
                        record.payload.get("confidence"),
                        payload_json,
                    ),
                )
            elif record.table == "shinkai_research_records":
                cursor.execute(
                    """
                    insert into shinkai_research_records(
                        record_type, record_id, run_id, payload, updated_at
                    )
                    values (%s, %s, %s, %s::jsonb, now())
                    on conflict (record_type, record_id) do update set
                        run_id = excluded.run_id,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (record.key[0], record.key[1], record.run_id, payload_json),
                )


def _parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _schema_statements() -> list[str]:
    return [
        """
        create table if not exists shinkai_state (
            section text primary key,
            payload jsonb not null,
            updated_at timestamptz not null default now()
        )
        """,
        """
        create table if not exists shinkai_runs (
            run_id text primary key,
            status text not null,
            mode text not null,
            anchor text not null,
            graph_id text,
            lifecycle_stage text not null,
            payload jsonb not null,
            updated_at timestamptz not null default now()
        )
        """,
        """
        create table if not exists shinkai_events (
            event_id text primary key,
            run_id text,
            type text not null,
            ts double precision,
            payload jsonb not null,
            updated_at timestamptz not null default now()
        )
        """,
        """
        create index if not exists shinkai_events_run_id_idx
            on shinkai_events(run_id, ts)
        """,
        """
        create table if not exists shinkai_graph_nodes (
            graph_id text not null,
            node_id text not null,
            run_id text,
            type text not null,
            label text not null,
            confidence double precision,
            payload jsonb not null,
            updated_at timestamptz not null default now(),
            primary key (graph_id, node_id)
        )
        """,
        """
        create index if not exists shinkai_graph_nodes_run_type_idx
            on shinkai_graph_nodes(run_id, type)
        """,
        """
        create table if not exists shinkai_research_records (
            record_type text not null,
            record_id text not null,
            run_id text,
            payload jsonb not null,
            updated_at timestamptz not null default now(),
            primary key (record_type, record_id)
        )
        """,
        """
        create index if not exists shinkai_research_records_run_type_idx
            on shinkai_research_records(run_id, record_type)
        """,
    ]


def normalized_records_for_section(section: str, value: Any) -> list[NormalizedRecord]:
    if not isinstance(value, dict):
        return []
    if section == "runs":
        return _run_records(value)
    if section == "graphs_by_run":
        return _graph_records(value)
    if section.startswith("research_"):
        return _research_records(section, value)
    return []


def _run_records(value: dict[str, Any]) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    for run_id, payload in value.items():
        if not isinstance(payload, dict):
            continue
        records.append(
            NormalizedRecord(
                table="shinkai_runs",
                key=(str(run_id),),
                run_id=str(run_id),
                payload=payload,
            )
        )
    return records


def _graph_records(value: dict[str, Any]) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    for run_id, payload in value.items():
        if not isinstance(payload, dict):
            continue
        graph_id = str(payload.get("graph_id") or "")
        for node in payload.get("nodes") or []:
            if isinstance(node, dict) and node.get("id"):
                records.append(
                    NormalizedRecord(
                        table="shinkai_graph_nodes",
                        key=(graph_id, str(node["id"])),
                        run_id=str(run_id),
                        payload=node,
                    )
                )
    return records


def _research_records(section: str, value: dict[str, Any]) -> list[NormalizedRecord]:
    id_key = {
        "research_sources": "source_id",
        "research_evidence": "evidence_id",
        "research_claims": "claim_id",
        "research_candidates": "candidate_id",
        "research_dossiers": "dossier_id",
        "research_tasks": "task_id",
    }.get(section)
    if id_key is None:
        return []
    records = []
    for record_id, payload in value.items():
        if not isinstance(payload, dict):
            continue
        records.append(
            NormalizedRecord(
                table="shinkai_research_records",
                key=(section.removeprefix("research_"), str(payload.get(id_key) or record_id)),
                run_id=_record_run_id(payload),
                payload=payload,
            )
        )
    return records


def _record_run_id(payload: dict[str, Any]) -> str | None:
    run_id = payload.get("run_id")
    if run_id:
        return str(run_id)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("run_id"):
        return str(metadata["run_id"])
    return None
