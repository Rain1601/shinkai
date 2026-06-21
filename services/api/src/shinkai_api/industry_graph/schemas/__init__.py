"""Industry graph schemas — Pydantic types only, no I/O.

Re-export the public surface so callers can ``from shinkai_api.industry_graph.schemas
import EntityBase, RelationBase, ProvenanceRef`` without reaching into submodules.
"""

from __future__ import annotations

from .entities import EntityBase, EntityKind
from .facets import FacetSet
from .ids import (
    bottleneck_id,
    company_id,
    component_id,
    key_data_id,
    product_id,
    region_id,
    relation_id,
    sector_id,
    slugify,
    source_id,
    subtheme_id,
    supply_layer_id,
    technology_id,
    theme_id,
    thesis_id,
    time_horizon_id,
)
from .provenance import EvidenceType, ProvenanceRef
from .relations import RelationBase, RelationType, WeightCell
from .snapshot import (
    ChangeEntry,
    ChangeKind,
    ChangeOp,
    ChangesetSummary,
    SnapshotMeta,
)

__all__ = [
    # Entity layer
    "EntityBase",
    "EntityKind",
    "FacetSet",
    # Provenance
    "ProvenanceRef",
    "EvidenceType",
    # Relation layer
    "RelationBase",
    "RelationType",
    "WeightCell",
    # Snapshot
    "SnapshotMeta",
    "ChangeEntry",
    "ChangeOp",
    "ChangeKind",
    "ChangesetSummary",
    # IDs
    "slugify",
    "theme_id",
    "subtheme_id",
    "technology_id",
    "company_id",
    "product_id",
    "component_id",
    "sector_id",
    "region_id",
    "supply_layer_id",
    "time_horizon_id",
    "bottleneck_id",
    "key_data_id",
    "thesis_id",
    "source_id",
    "relation_id",
]
