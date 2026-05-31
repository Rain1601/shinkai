from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.core.config import settings


class JsonStateFile:
    def __init__(self) -> None:
        self._lock = LoopBoundLock()

    async def load(self) -> dict[str, Any]:
        if not settings.persistence_enabled:
            return _empty_state()
        async with self._lock.get():
            path = self._path()
            if not path.exists():
                return _empty_state()
            return await asyncio.to_thread(_read_json, path)

    async def save_section(self, section: str, value: Any) -> None:
        if not settings.persistence_enabled:
            return
        async with self._lock.get():
            path = self._path()
            state = _empty_state()
            if path.exists():
                state.update(await asyncio.to_thread(_read_json, path))
            state[section] = value
            await asyncio.to_thread(_write_json, path, state)

    def _path(self) -> Path:
        path = Path(settings.state_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path


def _empty_state() -> dict[str, Any]:
    return {
        "runs": {},
        "graphs_by_run": {},
        "research_sources": {},
        "research_evidence": {},
        "research_claims": {},
        "research_candidates": {},
        "research_dossiers": {},
        "research_tasks": {},
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_state()
    if not isinstance(payload, dict):
        return _empty_state()
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


default_json_state = JsonStateFile()
