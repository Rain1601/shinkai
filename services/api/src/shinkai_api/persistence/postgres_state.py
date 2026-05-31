from __future__ import annotations

import asyncio
import json
from typing import Any

from shinkai_api.persistence.json_state import _empty_state


class PostgresStateFile:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def load(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._load_sync)

    async def save_section(self, section: str, value: Any) -> None:
        await asyncio.to_thread(self._save_section_sync, section, value)

    def _load_sync(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute("select section, payload from shinkai_state")
                rows = cursor.fetchall()
        state = _empty_state()
        for section, payload in rows:
            state[str(section)] = _parse_payload(payload)
        return state

    def _save_section_sync(self, section: str, value: Any) -> None:
        with self._connect() as connection:
            self._ensure_schema(connection)
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

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, autocommit=True)

    def _ensure_schema(self, connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                create table if not exists shinkai_state (
                    section text primary key,
                    payload jsonb not null,
                    updated_at timestamptz not null default now()
                )
                """
            )


def _parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload
