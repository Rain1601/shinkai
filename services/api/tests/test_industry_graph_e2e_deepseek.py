"""End-to-end test: DeepSeek drives the function-tool surface.

The LLM is given a short excerpt from a research report and asked to emit a
plan of ``{"calls": [...]}``. We dispatch the calls against an empty store
and assert the resulting state contains the expected facts.

Requires ``SHINKAI_DEEPSEEK_API_KEY``. Skips otherwise.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from shinkai_api.industry_graph import (
    INGESTION_SYSTEM_PROMPT,
    IndustryGraphStore,
    ToolDispatcher,
)
from shinkai_api.llm.deepseek import DeepSeekClient

# A compact excerpt distilled from MS 20260508 "Build for future AI infrastructure".
EXCERPT = """
Source: Morgan Stanley equity research, "Build for future AI infrastructure", May 8 2026.

NVIDIA Corporation (NVDA) — dominant GPU and AI accelerator designer.
- TSMC CoWoS is the gating constraint for NVDA Blackwell/Rubin GPU shipments
  in 2026. NVDA consumed 62% of all CoWoS capacity in 2025 and holds 59%
  in 2026e (875k of 1,479k total wafers).
- Primary HBM supplier for NVDA H200 is SK Hynix (sole on H200).
- Aspeed Technology (5274.TWO) supplies BMC chip used in every NVDA AI server.

Stocks to watch on the back of NVDA's CoWoS dominance:
- TSMC (2330.TW) — Necessary CoWoS exposure; AI semis revenue CAGR 60%.
- SK Hynix (000660.KS) — HBM primary supplier.
"""


def _has_key() -> bool:
    return bool(os.environ.get("SHINKAI_DEEPSEEK_API_KEY"))


@pytest.mark.skipif(not _has_key(), reason="SHINKAI_DEEPSEEK_API_KEY not set")
def test_deepseek_drives_ingestion(tmp_path: Path) -> None:
    """End-to-end smoke: DeepSeek emits calls, dispatcher executes, store
    ends up with NVDA + TSMC + a CoWoS bottleneck + a thesis."""

    async def run() -> None:
        store = IndustryGraphStore(root=tmp_path)
        await store.load()
        dispatcher = ToolDispatcher(store)
        client = DeepSeekClient(api_key=os.environ["SHINKAI_DEEPSEEK_API_KEY"])

        user_prompt = (
            f"{EXCERPT}\n\n"
            "Emit the ingestion plan. Pay attention to bottlenecks and "
            "stocks_to_watch — these are shinkai's alpha."
        )
        response = await client.chat_json(
            system=INGESTION_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.1,
            max_tokens=4000,
        )
        # The response may have extra keys we don't care about. Find the calls.
        calls = response.get("calls")
        assert isinstance(calls, list) and calls, (
            f"DeepSeek did not return a `calls` list. Response keys: "
            f"{list(response.keys())}"
        )

        results = await dispatcher.run_calls(calls)
        # Surface tool failures in test output for debugging.
        failures = [r for r in results if not r["ok"]]
        # We tolerate some failures (LLM hallucination of optional args) as long
        # as the headline facts landed.
        print(f"\n{len(results)} calls executed; {len(failures)} failed.")
        for f in failures[:5]:
            print(f"  ✗ {f['tool']}: {f['summary']}")

        # ----- assertions on store state -----
        # NVDA in store (label or alias contains NVDA / NVIDIA)
        nvda = store.index.find_by_ticker("NVDA") or store.index.get_entity("co:NVDA")
        assert nvda is not None, "NVDA entity not found in store"
        # TSMC in store
        tsmc = store.index.find_by_ticker("TSMC") or store.index.get_entity("co:TSMC")
        if tsmc is None:
            # Some LLM outputs use full company name slug.
            entities = store.index.list_by_kind("Company")
            tsmc_candidates = [
                e for e in entities
                if "tsmc" in " ".join(e.get("labels") or []).lower()
            ]
            assert tsmc_candidates, "TSMC entity not found"
        # At least one bottleneck
        bottlenecks = store.index.list_by_kind("Bottleneck")
        assert len(bottlenecks) >= 1, "No bottlenecks recorded"
        # At least one source
        sources = store.index.list_by_kind("Source")
        assert len(sources) >= 1, "No source registered"
        # Snapshot created (LLM was told to call create_snapshot)
        versions = await store.fs.list_snapshot_versions()
        assert len(versions) >= 1, "No snapshot committed"

    asyncio.run(run())


@pytest.mark.skipif(not _has_key(), reason="SHINKAI_DEEPSEEK_API_KEY not set")
def test_deepseek_response_contains_required_call_types(tmp_path: Path) -> None:
    """Sanity: the plan should at minimum include source + entity + relation."""

    async def run() -> None:
        client = DeepSeekClient(api_key=os.environ["SHINKAI_DEEPSEEK_API_KEY"])
        response = await client.chat_json(
            system=INGESTION_SYSTEM_PROMPT,
            user=EXCERPT,
            temperature=0.1,
            max_tokens=4000,
        )
        calls = response.get("calls") or []
        tools_called = {c.get("tool") for c in calls}
        required = {"register_source", "upsert_entity"}
        missing = required - tools_called
        assert not missing, (
            f"Missing required tool families: {missing}. Got: {tools_called}"
        )

    asyncio.run(run())


def test_dispatcher_handles_unknown_tool(tmp_path: Path) -> None:
    """Dispatcher should report an error rather than raising."""

    async def run() -> None:
        s = IndustryGraphStore(root=tmp_path)
        await s.load()
        d = ToolDispatcher(s)
        result = await d.dispatch("nonexistent_tool", {})
        assert not result.ok
        assert "Unknown tool" in result.summary

    asyncio.run(run())


def test_dispatcher_runs_calls_in_order(tmp_path: Path) -> None:
    """A deterministic plan (no LLM) goes through end-to-end."""

    async def run() -> None:
        s = IndustryGraphStore(root=tmp_path)
        await s.load()
        d = ToolDispatcher(s)
        plan = [
            {
                "tool": "register_source",
                "args": {
                    "publisher": "MS",
                    "title": "Test",
                    "date": "2026-05-08",
                },
            },
            {
                "tool": "upsert_entity",
                "args": {
                    "id": "co:NVDA",
                    "kind": "Company",
                    "labels": ["NVIDIA"],
                    "source_ref": {"source_id": "src:ms_2026_05_08_test"},
                },
            },
            {
                "tool": "create_snapshot",
                "args": {"rationale": "deterministic test"},
            },
        ]
        results = await d.run_calls(plan)
        assert all(r["ok"] for r in results), [
            r for r in results if not r["ok"]
        ]
        assert s.index.get_entity("co:NVDA") is not None
        versions = await s.fs.list_snapshot_versions()
        assert versions == [1]

    asyncio.run(run())
