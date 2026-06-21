"""Filesystem layout for the industry graph store.

All paths live under a single root, defaulting to ``.shinkai/industry_graph/``.
The root is overridable via the ``SHINKAI_INDUSTRY_GRAPH_PATH`` env var (so
tests can point at a tmpdir).

Layout (see ``docs/industry-graph-schema-v0.md`` §7):

    {root}/
        manifest.json
        current/
            targets/{name}.json
            shared/{companies,themes,technologies,sectors,regions,supply_layers,sources}.json
            meta.json
        snapshots/
            v{N:04d}/
                meta.json
                changes.jsonl
        audit.jsonl
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ROOT = Path(".shinkai/industry_graph")
ENV_ROOT_VAR = "SHINKAI_INDUSTRY_GRAPH_PATH"


def resolve_root(override: Path | None = None) -> Path:
    """Determine the root directory. Override > env var > default."""
    if override is not None:
        return override
    env_value = os.environ.get(ENV_ROOT_VAR)
    if env_value:
        return Path(env_value)
    return DEFAULT_ROOT


# Top-level files / subdirs
def manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def current_dir(root: Path) -> Path:
    return root / "current"


def snapshots_dir(root: Path) -> Path:
    return root / "snapshots"


def audit_path(root: Path) -> Path:
    return root / "audit.jsonl"


# Current state — sharded
def targets_dir(root: Path) -> Path:
    return current_dir(root) / "targets"


def shared_dir(root: Path) -> Path:
    return current_dir(root) / "shared"


def current_meta_path(root: Path) -> Path:
    return current_dir(root) / "meta.json"


def target_shard_path(root: Path, name: str) -> Path:
    """One file per target (anchor) — e.g. NVDA.json, AAPL.json, HBM.json."""
    return targets_dir(root) / f"{name}.json"


def shared_shard_path(root: Path, name: str) -> Path:
    """One file per shared category — e.g. companies.json, sources.json."""
    return shared_dir(root) / f"{name}.json"


# Snapshot directories
def snapshot_dir(root: Path, version: int) -> Path:
    return snapshots_dir(root) / f"v{version:04d}"


def snapshot_meta_path(root: Path, version: int) -> Path:
    return snapshot_dir(root, version) / "meta.json"


def snapshot_changes_path(root: Path, version: int) -> Path:
    return snapshot_dir(root, version) / "changes.jsonl"


# Known shared shard names
SHARED_SHARDS = (
    "companies",
    "themes",
    "subthemes",
    "technologies",
    "sectors",
    "regions",
    "supply_layers",
    "sources",
)
