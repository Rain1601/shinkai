"""ThemeEvent ingestion service.

Pipeline:
  Tavily news search  →  DeepSeek structurer  →  ThemeEvent records persisted

Both legs degrade independently:
- No Tavily key   ⇒ skip fetch, return empty summary with generator="no_tavily_key"
- No DeepSeek key ⇒ rule-based fallback (each raw hit becomes a low-relevance
                    industry event), generator="tavily_rule_fallback"
- DeepSeek error  ⇒ same fallback path, reject_reason recorded for the UI
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC
from typing import Any

from market_utils.core.errors import MarketUtilsError, NotConfigured
from market_utils.search import SearchEngine

from shinkai_api.core.config import settings
from shinkai_api.llm import DeepSeekClient, DeepSeekError
from shinkai_api.themes.events import (
    EventTier,
    ThemeEvent,
    ThemeEventSource,
    ThemeIngestionSummary,
    default_theme_event_store,
    make_event_id,
)

logger = logging.getLogger(__name__)


MAX_HITS_PER_THEME = 12
DEFAULT_NEWS_DAYS = 30
LLM_RELEVANCE_MIN = 0.25
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours


VALID_CATEGORIES: set[str] = {
    "earnings",
    "m_and_a",
    "product",
    "regulation",
    "supply_shock",
    "industry",
    "macro",
    "other",
}


def _parse_published_at(value: Any) -> float | None:
    """Tavily returns ``published_date`` either as ISO-8601 or YYYY-MM-DD."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Strip trailing Z to keep fromisoformat happy on 3.13 if any older format leaks.
    text = re.sub(r"Z$", "+00:00", text)
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        # Last-ditch: try date-only formats.
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                from datetime import datetime

                dt = datetime.strptime(text, fmt).replace(tzinfo=UTC)
                return dt.timestamp()
            except ValueError:
                continue
    return None


def _publisher_from_url(url: str) -> str:
    """Pull a coarse publisher label from the URL host."""
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        host = re.sub(r"^www\.", "", host)
        # Take the registrable domain (last two labels) — good enough for display.
        parts = host.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    except Exception:
        return ""


def _tier_for_publisher(publisher: str) -> EventTier:
    """Heuristic tier — major financial press → secondary, official → primary,
    everything else → tertiary. Pure heuristic; not load-bearing."""
    publisher = publisher.lower()
    if not publisher:
        return "tertiary"
    if any(p in publisher for p in ("sec.gov", "federalreserve.gov", "treasury.gov")):
        return "primary"
    if any(p in publisher for p in (
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com",
        "cnbc.com", "marketwatch.com", "barrons.com", "spglobal.com",
    )):
        return "secondary"
    return "tertiary"


# ---------------------------------------------------------------------------
# News fetch via market-utils (Google CSE / Tavily / DDG, caller-selected)
# ---------------------------------------------------------------------------


async def _fetch_news_hits(
    query: str,
    *,
    days: int,
    max_results: int,
    strategy: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch raw news hits via market-utils. Returns (hits, reject_reason).

    Strategies are isolated — passing ``"google"`` never falls through to
    Tavily, and vice versa. ``"auto"`` lets market-utils pick whichever
    backend has a configured key (tavily → google → duckduckgo).
    """
    date_restrict = f"d{max(1, min(days, 365))}"
    try:
        engine = SearchEngine.from_env(strategy=strategy)  # type: ignore[arg-type]
        results = await engine.search(
            query,
            max_results=max_results,
            date_restrict=date_restrict,
            topic="news",
        )
    except NotConfigured as exc:
        logger.info("news ingestion: %s not configured (%s)", strategy, exc)
        return [], f"not_configured: {exc}"
    except MarketUtilsError as exc:
        logger.warning("news ingestion (%s) failed: %s", strategy, exc)
        return [], f"backend_error: {exc}"

    hits = [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "published_date": r.published_at,
            "score": r.score,
            "backend": engine.strategy_name,
        }
        for r in results
    ]
    return hits, None


# ---------------------------------------------------------------------------
# Rule-based fallback (no LLM)
# ---------------------------------------------------------------------------


def _rule_fallback_event(theme_id: str, hit: dict[str, Any]) -> ThemeEvent | None:
    url = hit.get("url") or ""
    title = hit.get("title") or ""
    if not url or not title:
        return None
    publisher = _publisher_from_url(url)
    tier = _tier_for_publisher(publisher)
    ts = _parse_published_at(hit.get("published_date")) or time.time()
    return ThemeEvent(
        event_id=make_event_id(theme_id=theme_id, source_url=url, event_ts=ts, title=title),
        theme_id=theme_id,
        category="industry",
        event_ts=ts,
        title=title[:160],
        summary=str(hit.get("snippet") or "")[:280],
        key_facts=[],
        tickers=[],
        source=ThemeEventSource(
            url=url,
            title=title[:160],
            publisher=publisher,
            tier=tier,
            reliability=0.35,
        ),
        relevance=0.3,
        ingested_at=time.time(),
        metadata={"fallback": "rule"},
    )


# ---------------------------------------------------------------------------
# DeepSeek structurer
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are shinkai's market-event extractor for Chinese-speaking investors. "
    "For each raw news hit about a given investment research theme: "
    "(1) decide if it is genuinely relevant to the theme; "
    "(2) translate the title and write a concise summary IN SIMPLIFIED CHINESE "
    "regardless of the source language; "
    "(3) extract structured fields (category tag, key facts, tickers, relevance). "
    "Return STRICT JSON only — no commentary. Preserve proper nouns "
    "(company / product names) in their original form; do not invent facts."
)


def _user_prompt(theme_title: str, hits: list[dict[str, Any]]) -> str:
    listing = [
        {
            "idx": i,
            "title": h.get("title", ""),
            "url": h.get("url", ""),
            "snippet": (h.get("snippet") or "")[:600],
            "published_date": h.get("published_date") or "",
        }
        for i, h in enumerate(hits)
    ]
    return (
        f"Theme: {theme_title}\n\n"
        f"Raw news hits (each indexed):\n"
        + json.dumps(listing, ensure_ascii=False, indent=2)
        + "\n\nFor EACH hit, return one event object. Output JSON with this exact shape:\n"
        + json.dumps(
            {
                "events": [
                    {
                        "idx": 0,
                        "relevant": True,
                        "category": (
                            "earnings | m_and_a | product | regulation | "
                            "supply_shock | industry | macro | other"
                        ),
                        "title": "中文标题(简体中文,一行,保留公司名/产品名原文)",
                        "summary": "1-2 句中文摘要,事实陈述,不渲染",
                        "key_facts": ["关键事实 1(中文)", "关键事实 2(中文)"],
                        "tickers": ["NVDA", "TSM"],
                        "relevance": 0.0,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n\nRules:\n"
        + "- Every input hit MUST be answered (include idx).\n"
        + "- Set relevant=false when the hit is off-topic; we will skip it.\n"
        + "- category must be one of the listed enum values.\n"
        + "- tickers are US-listed 1-5 uppercase letters; omit foreign exchanges.\n"
        + "- relevance ∈ [0.0, 1.0]; below 0.25 will be filtered out client-side.\n"
        + "- Keep summary tight and factual; no marketing language.\n"
        + "- title / summary / key_facts MUST be Simplified Chinese.\n"
        + "- Preserve tickers, company names, product names in original form "
        + "(e.g. NVDA, TSMC, DeepSeek-V4-Pro). Do NOT translate ticker symbols.\n"
    )


def _validate_llm_events(
    raw: dict[str, Any],
    theme_id: str,
    hits: list[dict[str, Any]],
) -> list[ThemeEvent]:
    out: list[ThemeEvent] = []
    items = raw.get("events")
    if not isinstance(items, list):
        return out
    seen_idx: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("idx"))
        except (TypeError, ValueError):
            continue
        if idx in seen_idx or idx < 0 or idx >= len(hits):
            continue
        seen_idx.add(idx)
        if not item.get("relevant", True):
            continue
        hit = hits[idx]
        category = str(item.get("category") or "other").strip().lower()
        if category not in VALID_CATEGORIES:
            category = "other"
        try:
            relevance = float(item.get("relevance", 0.5))
        except (TypeError, ValueError):
            relevance = 0.5
        relevance = max(0.0, min(1.0, relevance))
        if relevance < LLM_RELEVANCE_MIN:
            continue
        title = str(item.get("title") or hit.get("title") or "").strip()
        if not title:
            continue
        url = str(hit.get("url") or "").strip()
        if not url:
            continue
        publisher = _publisher_from_url(url)
        tier = _tier_for_publisher(publisher)
        ts = _parse_published_at(hit.get("published_date")) or time.time()
        tickers_raw = item.get("tickers") or []
        tickers: list[str] = []
        if isinstance(tickers_raw, list):
            for t in tickers_raw:
                s = str(t or "").strip().upper()
                if re.fullmatch(r"[A-Z]{1,5}", s):
                    tickers.append(s)
        key_facts: list[str] = []
        kf_raw = item.get("key_facts") or []
        if isinstance(kf_raw, list):
            for f in kf_raw:
                s = str(f or "").strip()
                if s:
                    key_facts.append(s[:200])
        out.append(
            ThemeEvent(
                event_id=make_event_id(
                    theme_id=theme_id, source_url=url, event_ts=ts, title=title
                ),
                theme_id=theme_id,
                category=category,  # type: ignore[arg-type]
                event_ts=ts,
                title=title[:200],
                summary=str(item.get("summary") or "")[:600],
                key_facts=key_facts[:6],
                tickers=tickers[:8],
                source=ThemeEventSource(
                    url=url,
                    title=str(hit.get("title") or "")[:200],
                    publisher=publisher,
                    tier=tier,
                    reliability=0.5 if tier == "tertiary" else 0.7,
                ),
                relevance=relevance,
                ingested_at=time.time(),
                metadata={
                    "fetched_via": "tavily_news",
                    "tavily_score": hit.get("score"),
                },
            )
        )
    return out


async def _structure_with_llm(
    theme_title: str, theme_id: str, hits: list[dict[str, Any]]
) -> tuple[list[ThemeEvent], str | None]:
    """Returns (events, reject_reason). reject_reason non-None ⇒ caller should
    fall back to rule-based mapping."""
    if not settings.deepseek_api_key:
        return [], "no_deepseek_key"
    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.llm_model,
    )
    try:
        raw = await client.chat_json(
            system=_SYSTEM_PROMPT,
            user=_user_prompt(theme_title, hits),
            temperature=0.2,
            max_tokens=3000,
        )
    except DeepSeekError as exc:
        return [], f"deepseek_error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return [], f"unexpected: {exc}"
    events = _validate_llm_events(raw, theme_id, hits)
    if not events:
        return [], "no_valid_events_after_validation"
    return events, None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def ingest_theme(
    *,
    theme_id: str,
    theme_title: str,
    days: int = DEFAULT_NEWS_DAYS,
    force: bool = False,
    search_strategy: str = "auto",
) -> ThemeIngestionSummary:
    """Pull fresh news for one theme, structure with LLM, persist.

    Respects a 6h cache: if the last successful ingest is fresher than
    ``CACHE_TTL_SECONDS`` and ``force`` is False, returns the existing
    summary unchanged (no API spend).

    ``search_strategy`` is forwarded to market-utils:
    - ``"auto"`` (default) — picks the first configured backend
      (tavily → google → duckduckgo).
    - ``"google"`` / ``"tavily"`` / ``"duckduckgo"`` — explicit, no
      silent fall-through.
    """
    started = time.time()

    if not force:
        existing = await default_theme_event_store.get_summary(theme_id)
        if existing and started - existing.finished_at < CACHE_TTL_SECONDS:
            return existing

    # Force-refresh wipes the theme's events first so a re-ingest under a
    # newer LLM prompt (e.g. translation toggle) doesn't stack on top of the
    # old records — dedup by event_id only catches same-URL same-day, not
    # changes in prompt semantics.
    if force:
        await default_theme_event_store.clear_theme(theme_id)

    raw_hits, fetch_reject = await _fetch_news_hits(
        theme_title,
        days=days,
        max_results=MAX_HITS_PER_THEME,
        strategy=search_strategy,
    )

    if fetch_reject:
        summary = ThemeIngestionSummary(
            theme_id=theme_id,
            started_at=started,
            finished_at=time.time(),
            fetched_raw=0,
            structured=0,
            new_events=0,
            skipped_low_relevance=0,
            generator=f"{search_strategy}_unavailable",
            reject_reason=fetch_reject,
        )
        await default_theme_event_store.record_summary(summary)
        return summary

    if not raw_hits:
        summary = ThemeIngestionSummary(
            theme_id=theme_id,
            started_at=started,
            finished_at=time.time(),
            fetched_raw=0,
            structured=0,
            new_events=0,
            skipped_low_relevance=0,
            generator=f"{search_strategy}_empty",
            reject_reason="search returned zero hits",
        )
        await default_theme_event_store.record_summary(summary)
        return summary

    # Use the actual backend the engine picked when "auto" was requested.
    effective_backend = raw_hits[0].get("backend") or search_strategy

    events, reject_reason = await _structure_with_llm(theme_title, theme_id, raw_hits)
    generator = f"{effective_backend}+deepseek"

    if reject_reason:
        fallback_events: list[ThemeEvent] = []
        for hit in raw_hits:
            ev = _rule_fallback_event(theme_id, hit)
            if ev is not None:
                fallback_events.append(ev)
        events = fallback_events
        generator = f"{effective_backend}_rule_fallback"

    skipped = max(0, len(raw_hits) - len(events))
    new_count = await default_theme_event_store.upsert_many(events)

    summary = ThemeIngestionSummary(
        theme_id=theme_id,
        started_at=started,
        finished_at=time.time(),
        fetched_raw=len(raw_hits),
        structured=len(events),
        new_events=new_count,
        skipped_low_relevance=skipped,
        generator=generator,
        reject_reason=reject_reason,
    )
    await default_theme_event_store.record_summary(summary)
    return summary
