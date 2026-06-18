"""bridge_env_to_market_utils — verify NOISE_DOMAINS reach Vertex's
exclude_domains env so Google drops them before grounding (not after we waste
a grounding slot on them).
"""

from __future__ import annotations

import os

import pytest

from shinkai_api.core.config import bridge_env_to_market_utils
from shinkai_api.tools.source_filters import NOISE_DOMAINS


def test_bridge_populates_vertex_exclude_domains_from_noise_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MARKET_UTILS_VERTEX_EXCLUDE_DOMAINS", raising=False)
    bridge_env_to_market_utils()
    raw = os.environ.get("MARKET_UTILS_VERTEX_EXCLUDE_DOMAINS", "")
    domains = {d for d in raw.split(",") if d}
    # The set must include every NOISE_DOMAINS entry — these are the codified
    # SEO farms / affiliate spam we never want Google to ground on.
    assert NOISE_DOMAINS <= domains
    # Output is deterministic (sorted) so server restarts give the same string.
    assert raw == ",".join(sorted(domains))


def test_bridge_respects_existing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Operator override should win — letting someone hotfix bad domains
    # without a code deploy.
    monkeypatch.setenv("MARKET_UTILS_VERTEX_EXCLUDE_DOMAINS", "custom-noise.com")
    bridge_env_to_market_utils()
    assert os.environ["MARKET_UTILS_VERTEX_EXCLUDE_DOMAINS"] == "custom-noise.com"


def test_bridge_forwards_agent_search_when_engine_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MARKET_UTILS_AGENT_SEARCH_PROJECT", raising=False)
    monkeypatch.delenv("MARKET_UTILS_AGENT_SEARCH_ENGINE", raising=False)
    monkeypatch.setenv("SHINKAI_AGENT_SEARCH_PROJECT", "premium-proj")
    monkeypatch.setenv("SHINKAI_AGENT_SEARCH_ENGINE_ID", "premium-news-engine")
    # Force settings reload so env vars are picked up.
    from shinkai_api.core import config as cfg

    cfg.settings = cfg.Settings()
    cfg.bridge_env_to_market_utils()
    assert os.environ.get("MARKET_UTILS_AGENT_SEARCH_PROJECT") == "premium-proj"
    assert os.environ.get("MARKET_UTILS_AGENT_SEARCH_ENGINE") == "premium-news-engine"
