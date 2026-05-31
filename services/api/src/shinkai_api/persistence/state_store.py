from __future__ import annotations

import logging
from typing import Any

from shinkai_api.core.config import settings
from shinkai_api.persistence.json_state import JsonStateFile, _empty_state
from shinkai_api.persistence.postgres_state import PostgresStateFile

logger = logging.getLogger(__name__)


class StateStore:
    def __init__(self) -> None:
        self._json = JsonStateFile()
        self._postgres_disabled = False

    async def load(self) -> dict[str, Any]:
        if not settings.persistence_enabled:
            return _empty_state()
        postgres = self._postgres()
        if postgres is None:
            return await self._json.load()
        try:
            return await postgres.load()
        except Exception as exc:
            if not settings.persistence_json_fallback:
                raise
            logger.error(
                "postgres load failed; switching to JSON for remainder of process: %s", exc
            )
            self._postgres_disabled = True
            return await self._json.load()

    async def save_section(self, section: str, value: Any) -> None:
        if not settings.persistence_enabled:
            return
        postgres = self._postgres()
        if postgres is not None:
            try:
                await postgres.save_section(section, value)
                return
            except Exception as exc:
                if not settings.persistence_json_fallback:
                    raise
                logger.error(
                    "postgres save failed; switching to JSON for remainder of process: %s", exc
                )
                self._postgres_disabled = True
        await self._json.save_section(section, value)

    async def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        if not settings.persistence_enabled:
            return
        postgres = self._postgres()
        if postgres is None:
            return
        try:
            await postgres.append_event(run_id, event)
        except Exception as exc:
            if not settings.persistence_json_fallback:
                raise
            logger.error(
                "postgres event append failed; switching to JSON for remainder of process: %s",
                exc,
            )
            self._postgres_disabled = True

    async def query_events_by_type(
        self,
        event_type: str,
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        postgres = self._postgres()
        if postgres is None:
            return []
        try:
            return await postgres.query_events_by_type(event_type, run_id, limit)
        except Exception as exc:
            if not settings.persistence_json_fallback:
                raise
            logger.error("postgres event query failed: %s", exc)
            return []

    def _postgres(self) -> PostgresStateFile | None:
        if self._postgres_disabled or not settings.database_url:
            return None
        return PostgresStateFile(settings.database_url)


default_state_store = StateStore()
