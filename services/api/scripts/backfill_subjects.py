"""One-shot migration: materialize Subjects from the existing industry_graph.

Reads the current store, picks:
- Every ``Company`` entity with edge degree >= MIN_DEGREE (default 8)
- Every ``SubTheme`` entity (themes are first-class subjects regardless of degree)

For each one, creates:
- A ``Subject`` record (type=company|theme, target_entity_id pointing to the
  underlying entity).
- A synthetic ``SubjectVersion`` v1 with ``triggered_by="migration"``,
  ``snapshot_from = snapshot_to = <current head version>``,
  ``change_summary = None``, and ``scope_node_ids = []``. We do NOT fabricate
  scope or diff — the migration v1 just bookmarks "this Subject exists,
  starting from the current head".

Idempotent: re-running skips Subjects that already exist by id.

Usage::

    cd services/api
    uv run python scripts/backfill_subjects.py
    uv run python scripts/backfill_subjects.py --min-degree 4 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shinkai_api.industry_graph import IndustryGraphStore  # noqa: E402
from shinkai_api.industry_graph.subjects import (  # noqa: E402
    Subject,
    SubjectStore,
    SubjectVersion,
)

MIGRATION_RUN_ID = "migration"
MIGRATION_RATIONALE = "migration backfill, pre-existing state"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug_for_target(target_id: str) -> str:
    """Stable slug derived from a target entity id.

    ``co:NVDA`` → ``nvda``; ``co:2330.TW`` → ``2330_tw``; ``st:hbm`` → ``hbm``.
    """
    body = target_id.split(":", 1)[1] if ":" in target_id else target_id
    return _SLUG_RE.sub("_", body.lower()).strip("_") or body.lower()


def _pick_targets(
    graph: IndustryGraphStore, *, min_degree: int
) -> tuple[list[dict], list[dict]]:
    """Pick (companies, subthemes) eligible for backfill."""
    degree: Counter[str] = Counter()
    for r in graph.index.relations_by_id.values():
        if r.get("deprecated_at"):
            continue
        degree[r["source_id"]] += 1
        degree[r["target_id"]] += 1

    companies: list[dict] = []
    subthemes: list[dict] = []
    for e in graph.index.by_id.values():
        if e.get("deprecated_at"):
            continue
        kind = e.get("kind")
        if kind == "Company" and degree.get(e["id"], 0) >= min_degree:
            companies.append(e)
        elif kind == "SubTheme":
            subthemes.append(e)
    companies.sort(key=lambda e: -degree.get(e["id"], 0))
    subthemes.sort(key=lambda e: e.get("labels", [""])[0])
    return companies, subthemes


def _display_name(entity: dict) -> str:
    labels = entity.get("labels") or []
    return labels[0] if labels else entity["id"]


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--min-degree",
        type=int,
        default=8,
        help="Minimum edge degree for a Company to qualify (default 8).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without writing anything.",
    )
    args = p.parse_args()

    # Load the existing graph + subject store from the configured root.
    graph = IndustryGraphStore()
    await graph.load()
    subjects = SubjectStore(fs=graph.fs)
    await subjects.load()

    head = await graph.snapshots.latest_version()
    if head == 0:
        print("ERROR: no snapshots in store — run the seed ingestion first.")
        return 2

    companies, subthemes = _pick_targets(graph, min_degree=args.min_degree)
    candidates: list[tuple[str, dict]] = (
        [("company", e) for e in companies]
        + [("theme", e) for e in subthemes]
    )

    existing_ids = {s.id for s in await subjects.list_subjects()}
    created_subjects = 0
    created_versions = 0
    skipped = 0

    now = datetime.now(UTC)
    for subject_type, entity in candidates:
        slug = _slug_for_target(entity["id"])
        sid = f"subj:{slug}"
        if sid in existing_ids:
            skipped += 1
            continue
        subject = Subject(
            id=sid,
            type=subject_type,  # type: ignore[arg-type]
            display_name=_display_name(entity),
            target_entity_id=entity["id"],
            created_at=now,
            updated_at=now,
        )
        if args.dry_run:
            print(f"  + would create {sid:20} ({subject_type:7}) → {entity['id']}")
            created_subjects += 1
            created_versions += 1
            continue
        await subjects.upsert_subject(subject)
        version = SubjectVersion(
            id=f"sv:{slug}:1",
            subject_id=sid,
            version_no=1,
            run_id=MIGRATION_RUN_ID,
            snapshot_from=head,
            snapshot_to=head,
            triggered_by="migration",
            status="completed",
            started_at=now,
            ended_at=now,
            scope_node_ids=[],
            task_prompt="",
            rationale=MIGRATION_RATIONALE,
            change_summary=None,
        )
        await subjects.upsert_version(version)
        created_subjects += 1
        created_versions += 1
        print(f"  + {sid:20} ({subject_type:7}) → {entity['id']}")

    print()
    print(
        f"Done. Created {created_subjects} subjects + {created_versions} v1 "
        f"records; skipped {skipped} already-existing."
    )
    if args.dry_run:
        print("Dry run — nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
