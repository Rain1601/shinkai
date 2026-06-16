"""ThemeEvent — structured real-world events about a research theme.

A ThemeEvent is the *subject-side* counterpart to the agent's internal event
log: instead of "what the agent did" (run_start / hypothesis_created / ...),
this captures "what happened in the world that matters to this theme"
— earnings, M&A, product launches, regulatory shifts, supply shocks,
broader industry moves.

Each event is sourced from Tavily news / EDGAR filings, then structured by
DeepSeek into a normalized record with category + key facts + source ref.
Stored under the ``theme_events`` section keyed by event_id (deterministic
hash of source URL + published date so re-ingest does not duplicate).
"""

from __future__ import annotations

import hashlib
import time
from typing import Literal

from pydantic import BaseModel, Field

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.persistence import default_state_store

EventCategory = Literal[
    "earnings",
    "m_and_a",
    "product",
    "regulation",
    "supply_shock",
    "industry",
    "macro",
    "other",
]

EventTier = Literal[
    "primary",       # SEC filing, earnings release, official disclosure
    "secondary",     # Reuters / Bloomberg / FT / WSJ
    "tertiary",      # general web / blog / aggregator
    "agent_summary", # LLM-extracted with no real source
]


class ThemeEventSource(BaseModel):
    """A trimmed source-ref attached to each event. Mirrors research.SourceRef
    but kept independent so theme events do not depend on a run."""

    url: str = ""
    title: str = ""
    publisher: str = ""
    tier: EventTier = "tertiary"
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)


class ThemeEvent(BaseModel):
    event_id: str
    theme_id: str
    category: EventCategory = "other"
    event_ts: float  # POSIX seconds — when the real-world event happened
    title: str
    summary: str = ""
    key_facts: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    source: ThemeEventSource = Field(default_factory=ThemeEventSource)
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    ingested_at: float = Field(default_factory=time.time)
    metadata: dict = Field(default_factory=dict)


class ThemeIngestionSummary(BaseModel):
    """What happened on the last refresh of a theme."""

    theme_id: str
    started_at: float
    finished_at: float
    fetched_raw: int = 0      # raw search/filing hits returned
    structured: int = 0       # how many became ThemeEvents
    new_events: int = 0       # how many were not already persisted (dedup)
    skipped_low_relevance: int = 0
    generator: str = "empty"  # "tavily+deepseek" | "tavily_rule_fallback" | …
    reject_reason: str | None = None


def make_event_id(*, theme_id: str, source_url: str, event_ts: float, title: str = "") -> str:
    """Deterministic event_id so re-ingest of the same article never duplicates.

    Keyed on theme + URL + day. URL alone identifies a news article (one
    article = one canonical URL), so changes to the title via re-translation
    or LLM rerun must NOT change the id. ``title`` accepted for backward
    compat but ignored.
    """
    del title  # intentionally unused; URL is the canonical key
    h = hashlib.sha1()
    h.update(theme_id.encode("utf-8"))
    h.update(b"\0")
    h.update(source_url.encode("utf-8"))
    h.update(b"\0")
    # Bucket by day (UTC) so the same article re-fetched within a day dedups
    # even if Tavily's published_date wobbles by a few hours.
    day_bucket = int(event_ts) // 86400
    h.update(str(day_bucket).encode("utf-8"))
    return h.hexdigest()[:16]


class ThemeEventStore:
    """In-memory store backed by the JSON/Postgres state store.

    Layout in state:
      ``theme_events``           : { event_id: serialized ThemeEvent }
      ``theme_ingestion_log``    : { theme_id: serialized ThemeIngestionSummary }
    """

    SECTION_EVENTS = "theme_events"
    SECTION_LOG = "theme_ingestion_log"

    def __init__(self) -> None:
        self._events: dict[str, ThemeEvent] = {}
        self._log: dict[str, ThemeIngestionSummary] = {}
        self._lock = LoopBoundLock()
        self._loaded = False

    async def list_by_theme(self, theme_id: str) -> list[ThemeEvent]:
        async with self._lock.get():
            await self._ensure_loaded()
            events = [e for e in self._events.values() if e.theme_id == theme_id]
            events.sort(key=lambda e: e.event_ts, reverse=True)
            return events

    async def list_all(self, *, limit: int | None = None) -> list[ThemeEvent]:
        async with self._lock.get():
            await self._ensure_loaded()
            events = sorted(self._events.values(), key=lambda e: e.event_ts, reverse=True)
            if limit is not None:
                events = events[:limit]
            return events

    async def upsert_many(self, events: list[ThemeEvent]) -> int:
        async with self._lock.get():
            await self._ensure_loaded()
            new_count = 0
            for ev in events:
                if ev.event_id not in self._events:
                    new_count += 1
                self._events[ev.event_id] = ev
            await self._persist_events()
            return new_count

    async def clear_theme(self, theme_id: str) -> int:
        """Drop every event belonging to one theme. Returns count removed.

        Used by the force-refresh path so a re-ingest with a translated prompt
        replaces stale records instead of stacking on top of them.
        """
        async with self._lock.get():
            await self._ensure_loaded()
            removed = [ev_id for ev_id, ev in self._events.items() if ev.theme_id == theme_id]
            for ev_id in removed:
                del self._events[ev_id]
            if removed:
                await self._persist_events()
            return len(removed)

    async def record_summary(self, summary: ThemeIngestionSummary) -> ThemeIngestionSummary:
        async with self._lock.get():
            await self._ensure_loaded()
            self._log[summary.theme_id] = summary
            await self._persist_log()
            return summary

    async def get_summary(self, theme_id: str) -> ThemeIngestionSummary | None:
        async with self._lock.get():
            await self._ensure_loaded()
            return self._log.get(theme_id)

    async def all_summaries(self) -> dict[str, ThemeIngestionSummary]:
        async with self._lock.get():
            await self._ensure_loaded()
            return dict(self._log)

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_state_store.load()
        raw_events = state.get(self.SECTION_EVENTS)
        if isinstance(raw_events, dict):
            for ev_id, payload in raw_events.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    self._events[ev_id] = ThemeEvent.model_validate(payload)
                except Exception:
                    continue
        raw_log = state.get(self.SECTION_LOG)
        if isinstance(raw_log, dict):
            for theme_id, payload in raw_log.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    self._log[theme_id] = ThemeIngestionSummary.model_validate(payload)
                except Exception:
                    continue
        self._loaded = True

    async def _persist_events(self) -> None:
        await default_state_store.save_section(
            self.SECTION_EVENTS,
            {ev_id: ev.model_dump(mode="json") for ev_id, ev in self._events.items()},
        )

    async def _persist_log(self) -> None:
        await default_state_store.save_section(
            self.SECTION_LOG,
            {tid: s.model_dump(mode="json") for tid, s in self._log.items()},
        )

    def _reset_for_tests(self) -> None:
        self._events = {}
        self._log = {}
        self._loaded = False


default_theme_event_store = ThemeEventStore()
