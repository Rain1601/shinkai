"""Industry graph storage layer.

V0 surface:
- :mod:`paths`        — filesystem layout constants and helpers.
- :class:`IndustryGraphFileStore` — sharded JSON read/write with atomic semantics.

In-memory indices and snapshot diff layers land in later stages.
"""

from __future__ import annotations

from . import paths
from .file_store import IndustryGraphFileStore
from .memory_index import IndexLayer
from .snapshot import SnapshotManager, group_by_kind, make_change

__all__ = [
    "IndexLayer",
    "IndustryGraphFileStore",
    "SnapshotManager",
    "group_by_kind",
    "make_change",
    "paths",
]
