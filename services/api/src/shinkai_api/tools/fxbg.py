"""fxbaogao (发现报告) MCP HTTP client — Chinese sell-side research access.

Wraps the three tools exposed by https://api.fxbaogao.com/mcp/ as
ordinary shinkai Tools so the harness can search Chinese broker
research, pull hit-paragraphs without consuming download quota, and
fetch signed PDF URLs for the few reports worth full ingestion.

Auth: a single ``SHINKAI_FXBAOGAO_API_KEY`` env var (Bearer sk-xxx)
issued to Premium VIP subscribers. Without it the tools fail closed
with ``error="fxbaogao API key not configured"`` rather than calling
the endpoint anonymously.

Cost model (as of 2026-06): Premium VIP = 300 PDF downloads / month;
``search_reports`` and ``get_paragraphs`` are free. Phase 1 intent is
to default to paragraph-level ingestion and only spend download quota
when we promote a report to "must-read for thesis".

The MCP server returns JSON-RPC 2.0 envelopes; we unwrap ``result``,
parse the inner ``content[0].text`` (which the server JSON-encodes for
LLM consumption) back into structured data, and return a tidy
``ToolResult`` to the rest of shinkai.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from shinkai_api.tools.base import Tool, ToolResult

DEFAULT_ENDPOINT = "https://api.fxbaogao.com/mcp/"
_API_KEY_ENV = "SHINKAI_FXBAOGAO_API_KEY"
_ENDPOINT_ENV = "SHINKAI_FXBAOGAO_ENDPOINT"
_REQUEST_TIMEOUT_SECONDS = 30.0


def _get_api_key() -> str | None:
    return os.environ.get(_API_KEY_ENV) or None


def _get_endpoint() -> str:
    return os.environ.get(_ENDPOINT_ENV) or DEFAULT_ENDPOINT


async def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Single-shot JSON-RPC tools/call. Returns the parsed inner payload.

    Raises ``RuntimeError`` for any non-2xx response, JSON-RPC error
    envelope, or schema mismatch — the caller wraps these into
    ``ToolResult(ok=False, error=...)``.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("fxbaogao API key not configured")

    body = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # MCP HTTP transport accepts either plain JSON or SSE; we ask for both
        # so the server picks the cheapest path (which it does — plain JSON).
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(_get_endpoint(), json=body, headers=headers)
    response.raise_for_status()
    envelope = response.json()

    if "error" in envelope:
        err = envelope["error"]
        raise RuntimeError(f"fxbaogao MCP error: {err}")
    result = envelope.get("result") or {}

    # Prefer the structured payload when the server provides it (cleaner than
    # re-parsing the LLM-targeted text blob). Falls through to text parsing
    # for tools where structuredContent is omitted.
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured

    content = result.get("content") or []
    if content and isinstance(content[0], dict) and "text" in content[0]:
        text = content[0]["text"]
        try:
            return {"data": json.loads(text)}
        except (TypeError, ValueError):
            return {"data": text}
    return {"data": result}


class FxbgSearchTool(Tool):
    name = "fxbg_search"
    description = (
        "Search 发现报告 (fxbaogao) Chinese sell-side research by keyword, "
        "issuing institution, and time window. Returns matching reportIds, "
        "titles, publishers, and hit-paragraph previews — no download cost."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "keywords": {"type": "string"},
            "org_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional issuer whitelist (e.g. ['摩根士丹利','野村'])",
            },
            "start_time": {
                "type": "string",
                "description": "'last7day' | 'last1mon' | 'last3mon' | 'last1year' | ms timestamp",
            },
            "end_time": {
                "type": "string",
                "description": "End ms timestamp (rarely needed)",
            },
        },
        "required": ["keywords"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        keywords = str(kwargs.get("keywords") or "").strip()
        if not keywords:
            return ToolResult(ok=False, error="keywords is required")

        arguments: dict[str, Any] = {"keywords": keywords}
        if org_names := kwargs.get("org_names"):
            arguments["orgNames"] = list(org_names)
        if start_time := kwargs.get("start_time"):
            arguments["startTime"] = start_time
        if end_time := kwargs.get("end_time"):
            arguments["endTime"] = end_time

        try:
            payload = await _call_mcp_tool("search_reports", arguments)
        except (RuntimeError, httpx.HTTPError) as exc:
            return ToolResult(ok=False, error=str(exc))

        hits_raw = payload.get("data") or []
        hits = hits_raw if isinstance(hits_raw, list) else []
        return ToolResult(
            ok=True,
            summary=f"fxbg search '{keywords}': {len(hits)} hits",
            data={
                "keywords": keywords,
                "hits": hits,
                "hit_count": len(hits),
            },
        )


class FxbgParagraphsTool(Tool):
    name = "fxbg_paragraphs"
    description = (
        "Fetch a fxbaogao report's outline, abstract, and the paragraphs that "
        "matched a keyword — without spending download quota. Use this for "
        "thesis-density triage before deciding to fetch the full PDF."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "report_id": {"type": "integer", "minimum": 1},
            "keyword": {"type": "string"},
        },
        "required": ["report_id", "keyword"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            report_id = int(kwargs.get("report_id") or 0)
        except (TypeError, ValueError):
            return ToolResult(ok=False, error="report_id must be an integer")
        if report_id < 1:
            return ToolResult(ok=False, error="report_id must be >= 1")
        keyword = str(kwargs.get("keyword") or "").strip()
        if not keyword:
            return ToolResult(ok=False, error="keyword is required")

        try:
            payload = await _call_mcp_tool(
                "get_paragraphs",
                {"reportId": report_id, "keyword": keyword},
            )
        except (RuntimeError, httpx.HTTPError) as exc:
            return ToolResult(ok=False, error=str(exc))

        body = payload.get("data") if isinstance(payload, dict) else None
        return ToolResult(
            ok=True,
            summary=f"fxbg paragraphs reportId={report_id} keyword='{keyword}'",
            data={
                "report_id": report_id,
                "keyword": keyword,
                "paragraphs": body,
            },
        )


class FxbgPdfUrlTool(Tool):
    name = "fxbg_pdf_url"
    description = (
        "Issue a short-lived signed CDN URL for a fxbaogao report's PDF. "
        "Each call consumes one download from the account's monthly quota "
        "(300/month on Premium VIP). Use sparingly — prefer fxbg_paragraphs "
        "for triage."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "report_id": {"type": "integer", "minimum": 1},
        },
        "required": ["report_id"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            report_id = int(kwargs.get("report_id") or 0)
        except (TypeError, ValueError):
            return ToolResult(ok=False, error="report_id must be an integer")
        if report_id < 1:
            return ToolResult(ok=False, error="report_id must be >= 1")

        try:
            payload = await _call_mcp_tool(
                "get_pdf_url", {"reportId": report_id}
            )
        except (RuntimeError, httpx.HTTPError) as exc:
            return ToolResult(ok=False, error=str(exc))

        # structuredContent typically: {"code":0,"msg":"ok","data":"https://dr...pdf?auth_key=..."}
        body = payload if isinstance(payload, dict) else {}
        url = body.get("data") if isinstance(body.get("data"), str) else None
        if not url:
            return ToolResult(
                ok=False,
                error=f"fxbg_pdf_url: no url in response payload={body!r}",
            )
        return ToolResult(
            ok=True,
            summary=f"fxbg signed url for reportId={report_id}",
            data={"report_id": report_id, "pdf_url": url},
        )


async def download_pdf_from_url(
    url: str, dest_path: str, timeout: float = 60.0
) -> int:
    """Stream-download a signed fxbg URL to ``dest_path``. Returns bytes written.

    Kept as a helper rather than a Tool because the harness rarely needs to
    materialise PDFs itself — the ResearchGraph pipeline runs MinerU on a
    shared corpus directory. Used by scripts/fxbg_explore.py for manual
    pulls.
    """
    headers = {"referer": "https://www.fxbaogao.com/"}
    written = 0
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            with open(dest_path, "wb") as fp:
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    fp.write(chunk)
                    written += len(chunk)
    return written
