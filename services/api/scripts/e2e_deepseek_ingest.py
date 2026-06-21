"""Standalone E2E: ask DeepSeek to drive the industry-graph tool surface.

Loads ``SHINKAI_DEEPSEEK_API_KEY`` from ``services/api/.env`` if not in env,
sends a short research excerpt to DeepSeek, dispatches the returned tool
plan against an empty store, and prints what landed.

Usage (from services/api/)::

    uv run python scripts/e2e_deepseek_ingest.py [--root /tmp/ig.e2e]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shinkai_api.industry_graph import (  # noqa: E402
    INGESTION_SYSTEM_PROMPT,
    IndustryGraphStore,
    ToolDispatcher,
)
from shinkai_api.llm.deepseek import DeepSeekClient  # noqa: E402

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


def _load_dotenv() -> None:
    """Read services/api/.env into os.environ when keys are missing."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="/tmp/ig.e2e_deepseek", type=Path)
    p.add_argument("--max-tokens", default=4000, type=int)
    args = p.parse_args()

    _load_dotenv()
    api_key = os.environ.get("SHINKAI_DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: SHINKAI_DEEPSEEK_API_KEY not set.")
        return 2

    # Fresh store rooted at the args.root path
    import shutil

    if args.root.exists():
        shutil.rmtree(args.root)
    os.environ["SHINKAI_INDUSTRY_GRAPH_PATH"] = str(args.root)

    store = IndustryGraphStore(root=args.root)
    await store.load()
    dispatcher = ToolDispatcher(store)

    client = DeepSeekClient(api_key=api_key)
    print("Asking DeepSeek for an ingestion plan…")
    response = await client.chat_json(
        system=INGESTION_SYSTEM_PROMPT,
        user=EXCERPT,
        temperature=0.1,
        max_tokens=args.max_tokens,
    )
    calls = response.get("calls")
    if not isinstance(calls, list):
        print(f"ERROR: DeepSeek returned no 'calls' list. Keys: {list(response.keys())}")
        return 3
    print(f"Got {len(calls)} planned calls. Dispatching…")

    results = await dispatcher.run_calls(calls)
    failures = [r for r in results if not r["ok"]]
    print(f"\nExecuted {len(results)} calls; {len(failures)} failed.")
    for r in results:
        flag = "✓" if r["ok"] else "✗"
        print(f"  {flag} {r['tool']:>26}  {r['summary'][:80]}")

    # Summary
    print("\n--- Store state ---")
    s = store.stats()
    print(json.dumps(s, indent=2))
    print("\nEntities by kind:")
    for kind in sorted(store.index.by_kind):
        ents = store.index.list_by_kind(kind)
        print(f"  {kind:>20}: {len(ents):>3}")
    versions = await store.fs.list_snapshot_versions()
    print(f"\nSnapshots: {versions}")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
