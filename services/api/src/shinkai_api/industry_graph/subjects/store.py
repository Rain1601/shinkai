"""Persistence + concurrency for Subjects.

Two new shards live under ``current/shared/``:
- ``subjects.json``       — ``{subject_id: Subject.model_dump()}``
- ``subject_versions.json``— ``{sv_id: SubjectVersion.model_dump()}``

A per-subject asyncio lock guarantees that only one agent run can be in
flight against a given Subject at a time. This is enforced at the API layer
(POST /run) and surfaced as 409 to the caller when contended.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..store.file_store import IndustryGraphFileStore
from .models import (
    Subject,
    SubjectVersion,
    SubjectVersionStatus,
)

SUBJECTS_SHARD = "subjects"
SUBJECT_VERSIONS_SHARD = "subject_versions"


class SubjectLockBusy(RuntimeError):
    """Raised when a run is attempted on a Subject that already has one in flight."""


class SubjectStore:
    """Reads / writes Subject + SubjectVersion records.

    The store uses the same ``IndustryGraphFileStore`` shard mechanics as the
    rest of industry_graph so we don't introduce a parallel persistence layer.
    """

    def __init__(self, fs: IndustryGraphFileStore | None = None) -> None:
        self.fs = fs or IndustryGraphFileStore()
        # Per-subject-id asyncio.Lock for run serialization.
        self._run_locks: dict[str, asyncio.Lock] = {}
        # Guards in-memory subjects/versions dicts during read-modify-write.
        self._mem_lock = asyncio.Lock()
        self._subjects: dict[str, dict] = {}
        self._versions: dict[str, dict] = {}
        self._loaded = False

    # ---------- lifecycle ----------
    async def load(self) -> None:
        """Read both shards from disk into memory. Idempotent."""
        async with self._mem_lock:
            subjects = await self.fs.load_shared(SUBJECTS_SHARD) or {}
            versions = await self.fs.load_shared(SUBJECT_VERSIONS_SHARD) or {}
            self._subjects = dict(subjects)
            self._versions = dict(versions)
            self._loaded = True

    @property
    def root(self) -> Path:
        return self.fs.root

    # ---------- subject CRUD ----------
    async def list_subjects(self) -> list[Subject]:
        return [Subject.model_validate(s) for s in self._subjects.values()]

    async def get_subject(self, subject_id: str) -> Subject | None:
        raw = self._subjects.get(subject_id)
        if raw is None:
            return None
        return Subject.model_validate(raw)

    async def upsert_subject(self, subject: Subject) -> Subject:
        async with self._mem_lock:
            now = datetime.now(UTC)
            existing = self._subjects.get(subject.id)
            # Preserve created_at on update; always bump updated_at.
            if existing is not None and existing.get("created_at"):
                created_at = existing["created_at"]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
            else:
                created_at = subject.created_at or now
            record = subject.model_copy(update={"created_at": created_at, "updated_at": now})
            self._subjects[subject.id] = record.model_dump(mode="json")
            await self.fs.persist_shared(SUBJECTS_SHARD, dict(self._subjects))
            return record

    async def delete_subject(self, subject_id: str) -> bool:
        async with self._mem_lock:
            if subject_id not in self._subjects:
                return False
            self._subjects.pop(subject_id)
            await self.fs.persist_shared(SUBJECTS_SHARD, dict(self._subjects))
            return True

    # ---------- version CRUD ----------
    async def list_versions(self, subject_id: str) -> list[SubjectVersion]:
        """Return all SubjectVersion rows for a subject, oldest first."""
        rows = [
            SubjectVersion.model_validate(v)
            for v in self._versions.values()
            if v.get("subject_id") == subject_id
        ]
        return sorted(rows, key=lambda r: r.version_no)

    async def get_version(self, version_id: str) -> SubjectVersion | None:
        raw = self._versions.get(version_id)
        if raw is None:
            return None
        return SubjectVersion.model_validate(raw)

    async def latest_version_no(self, subject_id: str) -> int:
        """Highest existing version_no for the subject (0 if none yet)."""
        best = 0
        for v in self._versions.values():
            if v.get("subject_id") != subject_id:
                continue
            best = max(best, int(v.get("version_no", 0)))
        return best

    async def next_version_no(self, subject_id: str) -> int:
        return await self.latest_version_no(subject_id) + 1

    async def upsert_version(self, version: SubjectVersion) -> SubjectVersion:
        async with self._mem_lock:
            self._versions[version.id] = version.model_dump(mode="json")
            await self.fs.persist_shared(SUBJECT_VERSIONS_SHARD, dict(self._versions))
            return version

    async def update_version_status(
        self,
        version_id: str,
        *,
        status: SubjectVersionStatus,
        ended_at: datetime | None = None,
        error: str | None = None,
    ) -> SubjectVersion:
        async with self._mem_lock:
            raw = self._versions.get(version_id)
            if raw is None:
                raise KeyError(version_id)
            raw["status"] = status
            if ended_at is not None:
                raw["ended_at"] = ended_at.isoformat()
            if error is not None:
                raw["error"] = error
            self._versions[version_id] = raw
            await self.fs.persist_shared(SUBJECT_VERSIONS_SHARD, dict(self._versions))
            return SubjectVersion.model_validate(raw)

    # ---------- per-subject run lock ----------
    def _lock_for(self, subject_id: str) -> asyncio.Lock:
        lock = self._run_locks.get(subject_id)
        if lock is None:
            lock = asyncio.Lock()
            self._run_locks[subject_id] = lock
        return lock

    def is_run_in_flight(self, subject_id: str) -> bool:
        """True iff another coroutine currently holds the run lock."""
        lock = self._run_locks.get(subject_id)
        return bool(lock and lock.locked())

    @asynccontextmanager
    async def run_lock(self, subject_id: str):
        """Acquire the per-subject run lock non-blockingly; raise SubjectLockBusy
        if already held. asyncio.Lock has no built-in try_acquire, but checking
        ``locked()`` immediately before ``acquire()`` is race-free within a
        single event loop because there is no await between the two points.
        """
        lock = self._lock_for(subject_id)
        if lock.locked():
            raise SubjectLockBusy(subject_id)
        await lock.acquire()
        try:
            yield lock
        finally:
            lock.release()


__all__ = ["SubjectLockBusy", "SubjectStore", "SUBJECT_VERSIONS_SHARD", "SUBJECTS_SHARD"]
