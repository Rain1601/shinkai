"""Multi-facet classification axes.

An entity may sit on many independent axes at once: concept abstraction level,
industry sector, geography, value-chain position, time horizon. Facets are
deliberately a flat dict-like model with `extra="allow"` so adding a new axis
(e.g. ESG score, funding stage) is just appending a new field — no schema
migration required.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FacetSet(BaseModel):
    """Multi-axis tags. All fields optional. Forward-compatible: any unknown axis
    passed in at construction time is accepted via `extra="allow"`."""

    model_config = ConfigDict(extra="allow")

    # Concept abstraction (L1 Theme … L6+ Component); informational, not structural
    concept_level: int | None = None

    # Standard horizontal axes — all multi-valued
    sectors: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    chain_layers: list[str] = Field(default_factory=list)
    time_horizons: list[str] = Field(default_factory=list)
