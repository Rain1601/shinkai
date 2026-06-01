from __future__ import annotations

import asyncio
from typing import Any

import pytest

from shinkai_api.agent import harness as harness_module
from shinkai_api.core.config import settings
from shinkai_api.graph import default_graph_store
from shinkai_api.runs import RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor

ANCHORED_LAYER_NAMES = [
    "Power and electrical infrastructure",
    "Advanced packaging, HBM, and test capacity",
    "Cluster networking and optical interconnect",
    "Thermal systems and liquid cooling",
]


class _StubDeepSeek:
    """Replaces DeepSeekClient.chat_json to assert prompt content + return canned layers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.last_user: str = ""
        self.last_system: str = ""

    async def chat_json(self, *, system: str, user: str, **_: Any) -> dict[str, Any]:
        self.last_system = system
        self.last_user = user
        payload = dict(self.payload)
        payload.setdefault("_usage", {"input_tokens": 100, "output_tokens": 100})
        return payload


def _install_stub(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> _StubDeepSeek:
    stub = _StubDeepSeek(payload)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-stub")

    def factory(*_args: Any, **_kwargs: Any) -> _StubDeepSeek:
        return stub

    monkeypatch.setattr(harness_module, "DeepSeekClient", factory)
    return stub


def _quantum_payload() -> dict[str, Any]:
    return {
        "frontiers": [
            {
                "name": "Cryogenic dilution refrigeration",
                "seed_giants": ["IBM", "GOOG"],
                "bottleneck": "Quantum processors below 10 mK require helium-3 supply chains",
                "evidence_stub": "Helium-3 supplier capacity disclosures",
                "next_frontier": "Trace helium-3 reclamation tooling vendors",
                "companies": [
                    {"ticker": "ABCD", "name": "Cryo Vendor", "quality": 0.6, "underwater": 0.7},
                    {"ticker": "EFGH", "name": "Helium Co", "quality": 0.55, "underwater": 0.65},
                    {"ticker": "IJKL", "name": "Refrig Co", "quality": 0.5, "underwater": 0.8},
                ],
            },
            {
                "name": "Quantum control electronics",
                "seed_giants": ["IBM"],
                "bottleneck": "Microwave control fabric for qubit arrays is a bespoke supply",
                "evidence_stub": "Filings and 10-Ks of niche RF vendors",
                "next_frontier": "Map down to wafer-level packaging suppliers",
                "companies": [
                    {"ticker": "MNOP", "name": "Control Co", "quality": 0.62, "underwater": 0.6},
                    {"ticker": "QRST", "name": "Microwave Co", "quality": 0.58, "underwater": 0.7},
                    {"ticker": "UVWX", "name": "Packaging Co", "quality": 0.6, "underwater": 0.55},
                ],
            },
            {
                "name": "Photon detection arrays",
                "seed_giants": ["GOOG"],
                "bottleneck": "Single-photon detectors gate readout fidelity",
                "evidence_stub": "Patent filings for SNSPD arrays",
                "next_frontier": "Map cryo-CMOS readout integrators",
                "companies": [
                    {"ticker": "YZAB", "name": "Photon Co", "quality": 0.55, "underwater": 0.75},
                    {"ticker": "CDEF", "name": "Detector Co", "quality": 0.6, "underwater": 0.65},
                    {"ticker": "GHIJ", "name": "Optic Co", "quality": 0.5, "underwater": 0.7},
                ],
            },
        ],
        "review_policy": ["validate via primary filings"],
        "optimization_policy_patch": "spiral 2 must add SEC filing pulls",
    }


def test_llm_driven_run_uses_deepseek_proposals_and_drops_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        stub = _install_stub(monkeypatch, _quantum_payload())
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="Quantum computing supply chain",
                scope={
                    "objective": "find quantum-computing second-order suppliers",
                    "allow_live_sources": False,
                    "discovery_mode": "llm_driven",
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 60},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)
        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "completed"

        # Prompt must be theme-driven, not anchored on the four hardcoded layers.
        for hardcoded_name in ANCHORED_LAYER_NAMES:
            assert hardcoded_name not in stub.last_user, (
                f"hardcoded layer leaked into prompt: {hardcoded_name}"
            )
        assert "Quantum computing supply chain" in stub.last_user

        # The agent's frontier should be made of the stub's layers.
        layer_started = [
            event
            for event in current.events
            if event.type == "supply_chain_layer_started"
        ]
        layers_seen = {str(event.data.get("layer", "")) for event in layer_started}
        assert "Cryogenic dilution refrigeration" in layers_seen
        assert layers_seen.isdisjoint(set(ANCHORED_LAYER_NAMES))

        # planner_proposals is emitted with the LLM source and sample layers.
        proposals = [
            event for event in current.events if event.type == "planner_proposals"
        ]
        assert len(proposals) == 1
        proposal = proposals[0].data
        assert proposal["source"] == "deepseek_llm_planner"
        assert proposal["validated_layer_count"] == 3
        assert proposal["raw_frontier_count"] == 3
        assert proposal["reject_reason"] is None

    asyncio.run(scenario())


def test_invalid_llm_output_falls_back_when_not_forced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        bad_payload = {
            "frontiers": [
                {
                    "name": "Vague layer",
                    "bottleneck": "vague",
                    "next_frontier": "next",
                    "companies": [
                        {"ticker": "lowercase", "name": "x"},
                        {"ticker": "TOOLONGTICKER", "name": "y"},
                    ],
                }
            ]
        }
        _install_stub(monkeypatch, bad_payload)
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="AI compute infrastructure",
                scope={
                    "objective": "validate fallback path",
                    "allow_live_sources": False,
                    "discovery_mode": "auto",
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 80},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)
        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "completed"

        proposals = [
            event for event in current.events if event.type == "planner_proposals"
        ]
        assert len(proposals) == 1
        proposal = proposals[0].data
        assert proposal["source"] == "fallback_after_reject"
        assert proposal["reject_reason"]
        # Layer names should be the deterministic fallback set.
        assert proposal["sample_layers"][0] in ANCHORED_LAYER_NAMES

    asyncio.run(scenario())


def test_force_llm_planner_fails_when_output_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        bad_payload = {"frontiers": []}  # zero frontiers — definitely invalid
        _install_stub(monkeypatch, bad_payload)
        run = await default_run_store.create(
            RunCreate(
                mode="mode_b_narrative",
                anchor="AI compute infrastructure",
                scope={
                    "objective": "validate force_llm failure path",
                    "allow_live_sources": False,
                    "discovery_mode": "llm_driven",
                },
                budget={"max_wall_time_minutes": 120, "max_tool_calls": 40},
            )
        )
        graph = await default_graph_store.create_for_run(run)
        await default_run_store.set_graph_id(run.id, graph.graph_id)
        await default_run_executor.start(run.id)
        for _ in range(600):
            current = await default_run_store.get(run.id)
            if current.status in {"failed", "completed", "aborted"}:
                break
            await asyncio.sleep(0.05)

        current = await default_run_store.get(run.id)
        assert current.status == "failed", current.status

        proposals = [
            event for event in current.events if event.type == "planner_proposals"
        ]
        assert any(event.data["source"] == "force_llm_fail" for event in proposals)
        errors = [event for event in current.events if event.type == "error"]
        assert errors, "expected error event"
        assert "force_llm_planner" in errors[-1].data.get("message", "")

    asyncio.run(scenario())
