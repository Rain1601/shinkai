from __future__ import annotations

import asyncio
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from shinkai_api.core.config import settings
from shinkai_api.tools.base import Tool, ToolResult


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the public web for source-backed evidence."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        max_results = int(kwargs.get("max_results") or 3)
        if not query:
            return ToolResult(ok=False, error="query is required")
        # Prefer Tavily when the key is configured — it gives clean structured
        # results without the scraping fragility of duckduckgo's HTML page.
        backend = "duckduckgo"
        try:
            if settings.tavily_api_key:
                backend = "tavily"
                results = await asyncio.to_thread(
                    _tavily_search,
                    query,
                    max_results,
                    settings.tavily_api_key,
                    settings.tavily_base_url,
                )
            else:
                results = await asyncio.to_thread(
                    _duckduckgo_html_search, query, max_results
                )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=str(exc),
                summary=f"web search failed ({backend})",
                data={"backend": backend, "query": query},
            )
        return ToolResult(
            ok=bool(results),
            summary=f"Found {len(results)} web result(s) for: {query}",
            data={"query": query, "results": results, "backend": backend},
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


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_link = False
        self._in_snippet = False
        self._current_url = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        css_class = attrs_dict.get("class") or ""
        if tag == "a" and "result__a" in css_class:
            self._in_link = True
            self._current_url = _decode_duckduckgo_url(attrs_dict.get("href") or "")
            self._title_parts = []
            self._snippet_parts = []
        if tag in {"a", "div"} and "result__snippet" in css_class:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False
            title = html.unescape(" ".join(self._title_parts)).strip()
            if title and self._current_url:
                self.results.append(
                    {
                        "title": _clean_text(title),
                        "url": self._current_url,
                        "snippet": _clean_text(" ".join(self._snippet_parts)),
                    }
                )
        if tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._title_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)


def _tavily_search(
    query: str,
    max_results: int,
    api_key: str,
    base_url: str,
) -> list[dict[str, str]]:
    """Call Tavily search API and normalise to our ``results`` shape.

    Tavily docs: https://docs.tavily.com/docs/rest-api/api-reference
    We use ``search_depth=basic`` (faster, cheaper) and skip raw HTML.
    """
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(max_results, 10)),
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/search",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "shinkai-research-agent/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily HTTP {exc.code}: {detail[:200]}") from exc
    data = json.loads(raw)
    raw_results = data.get("results") or []
    out: list[dict[str, str]] = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": _clean_text(str(item.get("title") or "")),
                "url": str(item.get("url") or ""),
                "snippet": _clean_text(str(item.get("content") or "")),
                "score": str(item.get("score") or ""),
            }
        )
    return [item for item in out if item["url"]]


def _duckduckgo_html_search(query: str, max_results: int) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(
        f"https://duckduckgo.com/html/?{params}",
        headers={
            "User-Agent": "Mozilla/5.0 shinkai-research-bot/0.1",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        body = response.read().decode("utf-8", errors="replace")
    parser = _DuckDuckGoParser()
    parser.feed(body)
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in parser.results:
        url = result["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(result)
        if len(deduped) >= max_results:
            break
    return deduped


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


def _decode_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    if url.startswith("//"):
        return f"https:{url}"
    return url
