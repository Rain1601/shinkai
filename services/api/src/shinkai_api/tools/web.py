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

        try:
            engine = SearchEngine.from_env(strategy=strategy)  # type: ignore[arg-type]
            raw_results = await engine.search(
                query,
                max_results=max_results,
                date_restrict=date_restrict,
                topic=topic,
            )
        except NotConfigured as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"web search backend not configured ({strategy})",
                data={"backend": strategy, "query": query},
            )
        except QuotaExceeded as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"web search quota exceeded ({strategy})",
                data={"backend": strategy, "query": query},
            )
        except SearchTimeout as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"web search timed out ({strategy})",
                data={"backend": strategy, "query": query},
            )
        except MarketUtilsError as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"web search failed ({strategy})",
                data={"backend": strategy, "query": query},
            )

        results = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "source": r.source,
                "published_at": r.published_at,
                "score": (str(r.score) if r.score is not None else ""),
            }
            for r in raw_results
        ]
        return ToolResult(
            ok=bool(results),
            summary=f"Found {len(results)} web result(s) for: {query}",
            data={"query": query, "results": results, "backend": engine.strategy_name},
            error=None if results else "no results",
        )


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
