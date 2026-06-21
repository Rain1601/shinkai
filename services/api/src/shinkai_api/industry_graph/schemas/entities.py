"""Entity base schema.

V0 uses a single `EntityBase` model discriminated by the `kind` field. Per-kind
type-specific attributes live in the `attributes` dict (open-ended, no schema
change required to add fields). When a particular kind grows enough invariants
to deserve typed validation (e.g. Bottleneck always has type+severity), we add
a Pydantic model_validator. Until then, keep the schema flat and open.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .facets import FacetSet
from .provenance import ProvenanceRef

EntityKind = Literal[
    # Concept hierarchy (L1 -> L6+, dynamic depth)
    "Theme",
    "SubTheme",
    "Technology",
    "Company",
    "Product",
    "Component",
    # Horizontal facet entities (referenced by Company etc.)
    "Sector",
    "Region",
    "SupplyLayer",
    "TimeHorizon",
    # Analysis (shinkai alpha)
    "Bottleneck",
    "KeyDataPoint",
    "InvestmentThesis",
    # Source
    "Source",
]


class EntityBase(BaseModel):
    """Universal entity record.

    `id` is a stable URI (e.g. ``co:NVDA``, ``bn:cowos_capacity_2026``).
    `labels` carries display strings (can hold multiple languages); `aliases`
    carries tickers / shorthand / alternate names.
    `attributes` is the open-ended kind-specific payload — anything not modelled
    explicitly here lives there.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    kind: EntityKind
    labels: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    facets: FacetSet = Field(default_factory=FacetSet)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    snapshot_version: int = 0
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
