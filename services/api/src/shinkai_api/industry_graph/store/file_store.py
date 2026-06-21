"""Sharded JSON file store for the industry graph.

V0: single-user. Uses ``LoopBoundLock`` from ``core/async_lock`` to serialize
writes within one event loop. fcntl-level file locking is deferred to V1 when
multi-user support arrives.

All writes are atomic: write to a tmp file with the pid in its suffix, then
``os.replace`` swaps it in place. This mirrors the ``persistence/json_state.py``
pattern so the two stores stay consistent.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shinkai_api.core.async_lock import LoopBoundLock

from . import paths as p


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write ``payload`` to ``path`` atomically (tmp → replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _read_json(path: Path) -> Any:
    """Best-effort read. Returns ``None`` if missing; raises on corruption."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:  # surface corruption clearly
        raise RuntimeError(f"Corrupt JSON at {path}: {e}") from e


def _append_jsonl(path: Path, line: dict[str, Any]) -> None:
    """Append a single JSON object as one line to ``path`` (creating it if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, default=str))
        fh.write("\n")


def _iter_jsonl(path: Path):
    """Yield each JSON object from a ``.jsonl`` file. Empty/missing → no items."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            yield json.loads(raw)


class IndustryGraphFileStore:
    """Async wrapper around the sharded JSON layout.

    Construct with an optional ``root`` override; otherwise resolves via
    :func:`paths.resolve_root` (env var or default).

    All write methods acquire a single ``LoopBoundLock`` to ensure the
    on-disk shards stay consistent across concurrent coroutines.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = p.resolve_root(root)
        self._lock = LoopBoundLock()

    # ---------- target shards ----------
    async def load_target(self, name: str) -> dict[str, Any] | None:
        """Read one target shard. Returns ``None`` if absent."""
        path = p.target_shard_path(self.root, name)
        return await asyncio.to_thread(_read_json, path)

    async def persist_target(self, name: str, payload: dict[str, Any]) -> None:
        """Atomically write one target shard."""
        async with self._lock.get():
            path = p.target_shard_path(self.root, name)
            await asyncio.to_thread(_atomic_write_json, path, payload)

    async def list_targets(self) -> list[str]:
        """Names of the target shards present on disk (no extension)."""
        d = p.targets_dir(self.root)
        if not d.exists():
            return []
        return sorted(f.stem for f in d.glob("*.json"))

    # ---------- shared shards ----------
    async def load_shared(self, name: str) -> dict[str, Any] | None:
        path = p.shared_shard_path(self.root, name)
        return await asyncio.to_thread(_read_json, path)

    async def persist_shared(self, name: str, payload: dict[str, Any]) -> None:
        async with self._lock.get():
            path = p.shared_shard_path(self.root, name)
            await asyncio.to_thread(_atomic_write_json, path, payload)

    # ---------- manifest ----------
    async def load_manifest(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(_read_json, p.manifest_path(self.root))

    async def persist_manifest(self, payload: dict[str, Any]) -> None:
        async with self._lock.get():
            await asyncio.to_thread(_atomic_write_json, p.manifest_path(self.root), payload)

    # ---------- current snapshot meta ----------
    async def load_current_meta(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(_read_json, p.current_meta_path(self.root))

    async def persist_current_meta(self, payload: dict[str, Any]) -> None:
        async with self._lock.get():
            await asyncio.to_thread(
                _atomic_write_json, p.current_meta_path(self.root), payload
            )

    # ---------- snapshot directories (incremental diff) ----------
    async def list_snapshot_versions(self) -> list[int]:
        d = p.snapshots_dir(self.root)
        if not d.exists():
            return []
        versions = []
        for child in d.iterdir():
            if child.is_dir() and child.name.startswith("v"):
                try:
                    versions.append(int(child.name[1:]))
                except ValueError:
                    continue
        return sorted(versions)

    async def persist_snapshot(
        self,
        *,
        version: int,
        meta: dict[str, Any],
        changes: list[dict[str, Any]],
    ) -> None:
        """Write a snapshot's meta.json + changes.jsonl atomically (per file)."""
        async with self._lock.get():
            meta_path = p.snapshot_meta_path(self.root, version)
            changes_path = p.snapshot_changes_path(self.root, version)
            await asyncio.to_thread(_atomic_write_json, meta_path, meta)
            # Rewrite the changes file from scratch (atomic via tmp+replace).
            changes_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = changes_path.with_suffix(f".jsonl.{os.getpid()}.tmp")

            def _write_jsonl() -> None:
                with tmp.open("w", encoding="utf-8") as fh:
                    for c in changes:
                        fh.write(json.dumps(c, ensure_ascii=False, default=str))
                        fh.write("\n")
                tmp.replace(changes_path)

            await asyncio.to_thread(_write_jsonl)

    async def load_snapshot_meta(self, version: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(_read_json, p.snapshot_meta_path(self.root, version))

    async def load_snapshot_changes(self, version: int) -> list[dict[str, Any]]:
        path = p.snapshot_changes_path(self.root, version)
        return await asyncio.to_thread(lambda: list(_iter_jsonl(path)))

    # ---------- audit log (append-only) ----------
    async def append_audit(self, entry: dict[str, Any]) -> None:
        """Append one entry to ``audit.jsonl``. Caller supplies the timestamp
        when relevant; otherwise we stamp ``ts`` here for convenience."""
        entry = {"ts": datetime.now(UTC).isoformat(), **entry}
        async with self._lock.get():
            await asyncio.to_thread(_append_jsonl, p.audit_path(self.root), entry)

    async def read_audit(self) -> list[dict[str, Any]]:
        """Read the entire audit log. V0 only — paginate in V1."""
        path = p.audit_path(self.root)
        return await asyncio.to_thread(lambda: list(_iter_jsonl(path)))


__all__ = ["IndustryGraphFileStore"]
