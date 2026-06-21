"""Relation base schema + weight cell.

Like EntityBase, RelationBase is discriminated by `type` and holds per-type
data in `attributes`. The `weights` list captures time-series observations
(buyer_spend / lock_in / share_delta / …) per period. Each new weight key is
just a string in `WeightCell.values` — no schema change needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .provenance import ProvenanceRef

RelationType = Literal[
    # Hierarchy (concept tree)
    "contains",
    "is_a",
    "part_of",
    "variant_of",
    # Multi-facet tagging
    "themed_under",
    "uses_tech",
    "belongs_to_sector",
    "headquartered_in",
    # Value chain
    "supplies_to",
    "competes_with",
    "produces",
    # Analysis linkage
    "bottleneck_at",
    "affects",
    "key_data_about",
    "watched_in",
]


class WeightCell(BaseModel):
    """One observation in a relation's time series.

    `period` may be a fiscal year ("2026"), quarter ("2026Q1"), explicit estimate
    ("2026e"), or range ("2024..2027"). `values` is a dict because different
    relation types record different named weights; e.g. supplies_to carries
    `{buyer_spend, seller_revenue, lock_in}`, competes_with carries
    `{direct_overlap, share_delta}`. New dimensions are just new keys here.
    """

    model_config = ConfigDict(extra="allow")

    period: str
    values: dict[str, float] = Field(default_factory=dict)


class RelationBase(BaseModel):
    """Universal edge record.

    `id` is deterministic per (type, source_id, target_id, period) so re-ingesting
    the same fact does not duplicate edges. See ``ids.relation_id``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    type: RelationType
    source_id: str
    target_id: str
    weights: list[WeightCell] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    snapshot_version: int = 0
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
