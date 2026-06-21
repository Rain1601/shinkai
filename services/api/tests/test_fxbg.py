"""Tests for shinkai_api.tools.fxbg.

We mock out httpx at the module boundary rather than reaching for
respx — the project already uses plain monkeypatch in the rest of the
test suite, so we stay consistent. Three things are worth covering:

  1. Missing API key fails closed (no HTTP attempt).
  2. Happy path: server response → ToolResult shape we expect.
  3. JSON-RPC error envelope and HTTP error both become ToolResult.error.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from shinkai_api.tools import fxbg


class _FakeResponse:
    """Minimal stand-in for httpx.Response used by the tool."""

    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            req = httpx.Request("POST", "https://api.fxbaogao.com/mcp/")
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=req, response=httpx.Response(self.status_code)
            )

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient that records the call + returns a canned response."""

    instances: list[_FakeAsyncClient] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        self.last_url: str | None = None
        self.last_body: dict[str, Any] | None = None
        self.last_headers: dict[str, str] | None = None
        self.response: _FakeResponse = _FakeResponse(200, {})
        self.raise_with: Exception | None = None
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(  # noqa: A002
        self, url: str, *, json: dict[str, Any], headers: dict[str, str]
    ) -> _FakeResponse:
        self.last_url = url
        self.last_body = json
        self.last_headers = headers
        if self.raise_with is not None:
            raise self.raise_with
        return self.response


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch):
    """Swap httpx.AsyncClient in fxbg for our recorder, return the last instance."""
    _FakeAsyncClient.instances.clear()

    def make_client(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        return _FakeAsyncClient(*args, **kwargs)

    monkeypatch.setattr(fxbg.httpx, "AsyncClient", make_client)
    monkeypatch.setenv("SHINKAI_FXBAOGAO_API_KEY", "sk-test-1234")
    yield


# ---------------------------------------------------------------------------
# missing api key
# ---------------------------------------------------------------------------
def test_search_without_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHINKAI_FXBAOGAO_API_KEY", raising=False)
    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(tool.run(keywords="HBM"))
    assert result.ok is False
    assert "not configured" in (result.error or "")


# ---------------------------------------------------------------------------
# search happy path
# ---------------------------------------------------------------------------
def test_search_happy_path(fake_httpx) -> None:  # noqa: ARG001
    hits = [
        {"reportId": 1234, "title": "中际旭创深度", "orgName": "东方财富", "pageNum": 30},
        {"reportId": 5678, "title": "光模块周报", "orgName": "山西证券", "pageNum": 5},
    ]
    instance = _FakeAsyncClient()
    instance.response = _FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": json.dumps(hits)}],
            },
        },
    )
    _FakeAsyncClient.instances.clear()
    _FakeAsyncClient.instances.append(instance)
    # Monkeypatch the constructor to return our prepared instance
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]

    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(
        tool.run(keywords="中际旭创", org_names=["东方财富"], start_time="last3mon")
    )

    assert result.ok is True
    assert result.data["hit_count"] == 2
    assert result.data["hits"][0]["reportId"] == 1234
    # Verify Bearer header + JSON-RPC body shape
    assert instance.last_headers is not None
    assert instance.last_headers["Authorization"] == "Bearer sk-test-1234"
    assert instance.last_body is not None
    assert instance.last_body["method"] == "tools/call"
    assert instance.last_body["params"]["name"] == "search_reports"
    assert instance.last_body["params"]["arguments"]["keywords"] == "中际旭创"
    assert instance.last_body["params"]["arguments"]["orgNames"] == ["东方财富"]
    assert instance.last_body["params"]["arguments"]["startTime"] == "last3mon"


# ---------------------------------------------------------------------------
# paragraphs happy path
# ---------------------------------------------------------------------------
def test_paragraphs_happy_path(fake_httpx) -> None:  # noqa: ARG001
    inner = [{"pageNum": 1, "content": "1.6T 光模块率先放量..."}]
    instance = _FakeAsyncClient()
    instance.response = _FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(inner)}]},
        },
    )
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]

    tool = fxbg.FxbgParagraphsTool()
    result = asyncio.run(tool.run(report_id=5385254, keyword="硅光"))
    assert result.ok is True
    assert result.data["report_id"] == 5385254
    assert result.data["keyword"] == "硅光"
    assert result.data["paragraphs"][0]["content"].startswith("1.6T")


# ---------------------------------------------------------------------------
# pdf url uses structuredContent path
# ---------------------------------------------------------------------------
def test_pdf_url_structured_response(fake_httpx) -> None:  # noqa: ARG001
    signed = "https://dr.fxbaogao.com/report/2026/04/22/5385254.pdf?auth_key=abc"
    instance = _FakeAsyncClient()
    instance.response = _FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": f"已获取 PDF 下载地址：{signed}"}],
                "structuredContent": {"code": 0, "msg": "ok", "data": signed},
            },
        },
    )
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]

    tool = fxbg.FxbgPdfUrlTool()
    result = asyncio.run(tool.run(report_id=5385254))
    assert result.ok is True
    assert result.data["pdf_url"] == signed
    assert result.data["report_id"] == 5385254


# ---------------------------------------------------------------------------
# JSON-RPC error envelope → ToolResult.error
# ---------------------------------------------------------------------------
def test_jsonrpc_error_envelope_surfaces(fake_httpx) -> None:  # noqa: ARG001
    instance = _FakeAsyncClient()
    instance.response = _FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32602, "message": "Invalid params: keywords"},
        },
    )
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]

    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(tool.run(keywords="x"))
    assert result.ok is False
    assert "Invalid params" in (result.error or "")


# ---------------------------------------------------------------------------
# HTTP error → ToolResult.error
# ---------------------------------------------------------------------------
def test_http_error_surfaces(fake_httpx) -> None:  # noqa: ARG001
    instance = _FakeAsyncClient()
    req = httpx.Request("POST", "https://api.fxbaogao.com/mcp/")
    instance.raise_with = httpx.ConnectTimeout("upstream timeout", request=req)
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]

    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(tool.run(keywords="x"))
    assert result.ok is False
    assert "timeout" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# arg validation
# ---------------------------------------------------------------------------
def test_paragraphs_missing_keyword_rejects() -> None:
    tool = fxbg.FxbgParagraphsTool()
    result = asyncio.run(tool.run(report_id=1, keyword=""))
    assert result.ok is False
    assert "keyword" in (result.error or "")


def test_pdf_url_bad_id_rejects() -> None:
    tool = fxbg.FxbgPdfUrlTool()
    result = asyncio.run(tool.run(report_id=0))
    assert result.ok is False
    assert "report_id" in (result.error or "")


# ---------------------------------------------------------------------------
# default org whitelist + noise filter
# ---------------------------------------------------------------------------
def _mk_instance(hits: list[dict[str, Any]]) -> _FakeAsyncClient:
    instance = _FakeAsyncClient()
    instance.response = _FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(hits)}]},
        },
    )
    return instance


def test_search_default_org_whitelist_is_applied(fake_httpx) -> None:  # noqa: ARG001
    instance = _mk_instance([])
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]
    tool = fxbg.FxbgSearchTool()
    asyncio.run(tool.run(keywords="HBM"))
    assert instance.last_body is not None
    assert instance.last_body["params"]["arguments"]["orgNames"] == list(
        fxbg.PREFERRED_ORG_NAMES
    )


def test_search_explicit_org_overrides_default(fake_httpx) -> None:  # noqa: ARG001
    instance = _mk_instance([])
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]
    tool = fxbg.FxbgSearchTool()
    asyncio.run(tool.run(keywords="HBM", org_names=["东方财富"]))
    assert instance.last_body is not None
    assert instance.last_body["params"]["arguments"]["orgNames"] == ["东方财富"]


def test_search_use_default_orgs_false_omits_filter(fake_httpx) -> None:  # noqa: ARG001
    instance = _mk_instance([])
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]
    tool = fxbg.FxbgSearchTool()
    asyncio.run(tool.run(keywords="HBM", use_default_orgs=False))
    assert instance.last_body is not None
    assert "orgNames" not in instance.last_body["params"]["arguments"]


def test_noise_org_and_tiny_pages_filtered(fake_httpx) -> None:  # noqa: ARG001
    hits = [
        {"reportId": 1, "title": "real deep", "orgName": "高盛", "pageNum": 30},
        {"reportId": 2, "title": "rumor", "orgName": "未知机构", "pageNum": 1},
        {"reportId": 3, "title": "chartpack", "orgName": "摩根士丹利", "pageNum": 2},
        {"reportId": 4, "title": "real medium", "orgName": "野村", "pageNum": 10},
    ]
    instance = _mk_instance(hits)
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]
    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(tool.run(keywords="HBM"))
    assert result.ok is True
    assert result.data["hit_count"] == 2
    assert {h["reportId"] for h in result.data["hits"]} == {1, 4}
    assert result.data["dropped_noise"] == 1
    assert result.data["dropped_tiny"] == 1
    assert result.data["raw_count"] == 4


def test_min_pages_override(fake_httpx) -> None:  # noqa: ARG001
    hits = [
        {"reportId": 1, "title": "two pager", "orgName": "高盛", "pageNum": 2},
        {"reportId": 2, "title": "five pager", "orgName": "高盛", "pageNum": 5},
    ]
    instance = _mk_instance(hits)
    fxbg.httpx.AsyncClient = lambda *a, **k: instance  # type: ignore[assignment]
    tool = fxbg.FxbgSearchTool()
    result = asyncio.run(tool.run(keywords="HBM", min_pages=0))
    assert result.data["hit_count"] == 2  # both kept when threshold is 0
