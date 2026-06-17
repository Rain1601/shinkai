from __future__ import annotations

import asyncio
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from market_utils.core.errors import (
    MarketUtilsError,
    NotConfigured,
    QuotaExceeded,
    SearchTimeout,
)
from market_utils.search import SearchEngine

from shinkai_api.core.config import bridge_env_to_market_utils, settings
from shinkai_api.tools.base import Tool, ToolResult
from shinkai_api.tools.source_filters import is_aggregator_source, is_noise_source

# Order in which we try search backends when the caller asks for "auto", or
# when the requested backend fails transiently. Mirrors market-utils' own
# preference list so behaviour stays predictable across the stack.
_FALLBACK_CHAIN: tuple[str, ...] = ("vertex_grounding", "tavily", "google", "duckduckgo")

# Single-retry backoff for QuotaExceeded on the primary strategy. Vertex
# returns 429 in bursts — one short sleep clears most of them; if it doesn't,
# we fall back rather than spending more time waiting.
_PRIMARY_QUOTA_BACKOFF_SECONDS = 1.0


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the public web for source-backed evidence."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
            "strategy": {
                "type": "string",
                "enum": [
                    "auto",
                    "vertex_grounding",
                    "agent_search",
                    "google",
                    "tavily",
                    "duckduckgo",
                ],
                "default": "auto",
            },
            "topic": {"type": "string", "enum": ["news"]},
            "date_restrict": {"type": "string"},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        max_results = int(kwargs.get("max_results") or 3)
        strategy = str(kwargs.get("strategy") or settings.web_search_strategy or "auto")
        topic = kwargs.get("topic") or None
        date_restrict = kwargs.get("date_restrict") or None
        if not query:
            return ToolResult(ok=False, error="query is required")

        bridge_env_to_market_utils()

        attempt_order = _build_attempt_order(strategy)
        attempts: list[dict[str, str]] = []
        raw_results: list[Any] = []
        engine_name = ""
        for index, candidate in enumerate(attempt_order):
            try:
                engine_name, raw_results = await _run_strategy(
                    candidate, query, max_results, date_restrict, topic
                )
                break
            except QuotaExceeded as exc:
                # Burst 429 on the primary clears with a short sleep often
                # enough to be worth one retry before falling back.
                if index == 0:
                    await asyncio.sleep(_PRIMARY_QUOTA_BACKOFF_SECONDS)
                    try:
                        engine_name, raw_results = await _run_strategy(
                            candidate, query, max_results, date_restrict, topic
                        )
                        break
                    except (
                        QuotaExceeded,
                        NotConfigured,
                        SearchTimeout,
                        MarketUtilsError,
                    ) as exc2:
                        attempts.append(
                            {"strategy": candidate, "error": f"retry_failed: {exc2}"}
                        )
                        continue
                attempts.append({"strategy": candidate, "error": f"quota_exceeded: {exc}"})
                continue
            except NotConfigured as exc:
                attempts.append({"strategy": candidate, "error": f"not_configured: {exc}"})
                continue
            except SearchTimeout as exc:
                attempts.append({"strategy": candidate, "error": f"timeout: {exc}"})
                continue
            except MarketUtilsError as exc:
                attempts.append({"strategy": candidate, "error": f"backend_error: {exc}"})
                continue
        else:
            return ToolResult(
                ok=False,
                error="all configured search backends failed",
                summary=f"web search exhausted {len(attempts)} backend(s) for: {query}",
                data={"query": query, "attempts": attempts},
            )

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        noise_dropped = 0
        for r in raw_results:
            url_l = (r.url or "").strip().lower()
            if not url_l or url_l in seen_urls:
                # Vertex Grounding pass-2 occasionally returns the same SEO
                # page multiple times — drop exact-URL duplicates.
                continue
            if is_noise_source(r.url, r.source or ""):
                noise_dropped += 1
                continue
            seen_urls.add(url_l)
            results.append(
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": r.source,
                    "published_at": r.published_at,
                    "score": (str(r.score) if r.score is not None else ""),
                    "is_aggregator": is_aggregator_source(r.url, r.source or ""),
                }
            )
        return ToolResult(
            ok=bool(results),
            summary=f"Found {len(results)} web result(s) for: {query}",
            data={
                "query": query,
                "results": results,
                "backend": engine_name,
                "noise_dropped": noise_dropped,
                "attempts": attempts,
            },
            error=None if results else "no results",
        )


def _build_attempt_order(strategy: str) -> list[str]:
    """Return the ordered list of backends to try.

    - "auto" → the default fallback chain in order
    - explicit strategy → [strategy, then chain members excluding it]
    """
    if strategy == "auto":
        return list(_FALLBACK_CHAIN)
    fallback_tail = [s for s in _FALLBACK_CHAIN if s != strategy]
    return [strategy, *fallback_tail]


async def _run_strategy(
    strategy: str,
    query: str,
    max_results: int,
    date_restrict: str | None,
    topic: str | None,
) -> tuple[str, list[Any]]:
    engine = SearchEngine.from_env(strategy=strategy)  # type: ignore[arg-type]
    raw = await engine.search(
        query,
        max_results=max_results,
        date_restrict=date_restrict,
        topic=topic,
    )
    return engine.strategy_name, raw


class WebExtractTool(Tool):
    name = "web_extract"
    description = "Fetch a webpage and extract a compact text excerpt."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if not url:
            return ToolResult(ok=False, error="url is required")
        try:
            extracted = await asyncio.to_thread(_extract_url, url)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=str(exc), summary="web extract failed")
        return ToolResult(ok=True, summary=extracted["title"], data=extracted)


def _extract_url(url: str) -> dict[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 shinkai-research-bot/0.1",
            "Accept": "text/html,text/plain",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        content_type = response.headers.get("content-type", "")
        raw = response.read(400_000).decode("utf-8", errors="replace")
    text = raw if "text/plain" in content_type else _html_to_text(raw)
    return {
        "url": url,
        "title": _extract_title(raw) or url,
        "excerpt": _clean_text(text)[:1200],
    }


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def _extract_title(raw: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if not match:
        return ""
    return _clean_text(html.unescape(match.group(1)))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
