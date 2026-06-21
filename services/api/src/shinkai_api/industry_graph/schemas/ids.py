"""Stable ID conventions.

IDs are ``{prefix}:{slug}``. Prefix encodes the entity kind; slug is a
short, human-readable, lowercase identifier. Slugs go through ``slugify`` so
arbitrary labels become safe identifiers.

Relations get deterministic IDs derived from ``(type, source_id, target_id,
period)`` so re-ingesting the same fact does not create duplicate edges.

Note: ``InvestmentThesis`` uses the ``ith`` prefix to avoid colliding with
``Theme`` which uses ``th``. (Spec §6 originally read ``th:`` for both;
collision avoidance forces the rename.)
"""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(label: str) -> str:
    """Lowercase, collapse non-alphanumeric runs into ``_``, strip ends."""
    return _SLUG_RE.sub("_", label.lower()).strip("_")


def _id(prefix: str, slug: str) -> str:
    return f"{prefix}:{slug}"


# Concept hierarchy
def theme_id(slug: str) -> str:
    return _id("th", slugify(slug))


def subtheme_id(slug: str) -> str:
    return _id("st", slugify(slug))


def technology_id(slug: str) -> str:
    return _id("tech", slugify(slug))


def company_id(ticker_or_slug: str) -> str:
    """Companies keep ticker case (NVDA stays NVDA); other names go through slugify
    but non-ASCII labels (e.g. ``绿的谐波``) are preserved verbatim."""
    looks_like_ticker = ticker_or_slug.isascii() and ticker_or_slug == ticker_or_slug.upper()
    if looks_like_ticker:
        return _id("co", ticker_or_slug)
    if not ticker_or_slug.isascii():
        return _id("co", ticker_or_slug)
    return _id("co", slugify(ticker_or_slug))


def product_id(slug: str) -> str:
    return _id("pd", slugify(slug))


def component_id(slug: str) -> str:
    return _id("cmp", slugify(slug))


# Horizontal facet entities
def sector_id(slug: str) -> str:
    return _id("sec", slugify(slug))


def region_id(code: str) -> str:
    return _id("reg", code.upper())


def supply_layer_id(slug: str) -> str:
    return _id("lay", slugify(slug))


def time_horizon_id(slug: str) -> str:
    return _id("hor", slugify(slug))


# Analysis
def bottleneck_id(slug: str) -> str:
    return _id("bn", slugify(slug))


def key_data_id(slug: str) -> str:
    return _id("kdp", slugify(slug))


def thesis_id(slug: str) -> str:
    # `ith` = investment thesis, avoiding clash with theme `th`
    return _id("ith", slugify(slug))


# Source
def source_id(slug: str) -> str:
    return _id("src", slugify(slug))


# Relations: deterministic from (type, source_id, target_id, period)
def relation_id(rel_type: str, source_id: str, target_id: str, period: str | None = None) -> str:
    """Deterministic relation ID — re-ingesting the same edge is idempotent.

    ``:`` inside source/target IDs is rewritten to ``_`` so the relation ID
    has a single ``:`` after the ``r`` prefix.
    """
    s = source_id.replace(":", "_")
    t = target_id.replace(":", "_")
    parts = [rel_type, s, t]
    if period:
        parts.append(period)
    return "r:" + "~".join(parts)
