from __future__ import annotations

from typing import Any

from shinkai_api.core.config import settings
from shinkai_api.persistence.json_state import JsonStateFile, _empty_state
from shinkai_api.persistence.postgres_state import PostgresStateFile


class StateStore:
    def __init__(self) -> None:
        self._json = JsonStateFile()

    async def load(self) -> dict[str, Any]:
        if not settings.persistence_enabled:
            return _empty_state()
        postgres = self._postgres()
        if postgres is None:
            return await self._json.load()
        try:
            return await postgres.load()
        except Exception:
            if not settings.persistence_json_fallback:
                raise
            return await self._json.load()

    async def save_section(self, section: str, value: Any) -> None:
        if not settings.persistence_enabled:
            return
        postgres = self._postgres()
        if postgres is not None:
            try:
                await postgres.save_section(section, value)
                return
            except Exception:
                if not settings.persistence_json_fallback:
                    raise
        await self._json.save_section(section, value)

    def _postgres(self) -> PostgresStateFile | None:
        if not settings.database_url:
            return None
        return PostgresStateFile(settings.database_url)


default_state_store = StateStore()
