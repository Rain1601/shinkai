"""Theme grouping for runs.

A *theme* is the natural cross-run aggregation unit — multiple runs against the
same investment anchor (e.g. "AI infrastructure") are grouped under one theme.
The theme id is a deterministic slug of the anchor string so the same anchor
across two runs maps to the same id.
"""

from __future__ import annotations

import re


def theme_key(anchor: str) -> str:
    """Return a stable slug from a run anchor.

    Lowercased, whitespace collapsed, non-alphanumeric replaced with ``-``.
    Empty anchors fall back to ``autonomous-discovery`` to keep the default
    theme of the autonomous scan stable.
    """
    cleaned = (anchor or "").strip().lower()
    if not cleaned:
        return "autonomous-discovery"
    cleaned = re.sub(r"\s+", " ", cleaned)
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return slug or "autonomous-discovery"
