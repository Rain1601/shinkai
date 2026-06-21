"""Real agent loop: DeepSeek drives industry-graph tools, no research text input.

Workflow:
1. Load the seeded store (run ``ingest_supply_chain_graph_seed.py`` first).
2. Hand the agent a one-sentence task plus the tool catalogue.
3. The agent explores with query tools, then makes targeted writes.
4. Stop on ``{"tool": "done"}`` or turn budget exhaustion.

Usage::

    uv run python scripts/e2e_deepseek_agent.py \\
        --root /tmp/ig.agent \\
        --seed-from /Users/rain/ResearchGraph/data/sop_v1/supply_chain_graph.json \\
        --task "Add 1 tech bottleneck and 2 KeyDataPoints to NVDA." \\
        --max-turns 15
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shinkai_api.industry_graph import AgentLoop, IndustryGraphStore  # noqa: E402
from shinkai_api.llm.deepseek import DeepSeekClient  # noqa: E402


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


DEFAULT_TASK = (
    "Investigate NVDA's existing supply chain in the graph. "
    "Then add exactly ONE new Bottleneck (type=technology, severity=medium) "
    "describing a plausible 2027 risk that the graph does not yet capture, "
    "and ONE new KeyDataPoint about NVDA's expected 2027 GPU shipment growth. "
    "Take a snapshot before declaring done."
)


async def _ingest_seed(seed_path: Path) -> int:
    """Reuse the existing seed script via inline import."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ingest_supply_chain_graph_seed as seed  # type: ignore

    sys.argv = ["seed", str(seed_path), "--rationale", "agent session seed"]
    return await seed.main()


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="/tmp/ig.agent", type=Path)
    p.add_argument("--seed-from", type=Path, default=None,
                   help="Optional path to supply_chain_graph.json to seed the store first.")
    p.add_argument("--task", default=DEFAULT_TASK)
    p.add_argument("--max-turns", type=int, default=15)
    p.add_argument("--max-tokens", type=int, default=1500)
    p.add_argument("--temperature", type=float, default=0.2)
    args = p.parse_args()

    _load_dotenv()
    api_key = os.environ.get("SHINKAI_DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: SHINKAI_DEEPSEEK_API_KEY not set (check services/api/.env).")
        return 2

    # Fresh root and optional seed.
    if args.root.exists():
        shutil.rmtree(args.root)
    os.environ["SHINKAI_INDUSTRY_GRAPH_PATH"] = str(args.root)

    if args.seed_from:
        print(f"Seeding store from {args.seed_from}…")
        await _ingest_seed(args.seed_from)

    store = IndustryGraphStore(root=args.root)
    await store.load()
    print(f"Store loaded. Pre-agent stats: {store.stats()}")

    client = DeepSeekClient(api_key=api_key)
    loop = AgentLoop(
        store=store,
        client=client,
        task=args.task,
        max_turns=args.max_turns,
        max_tokens_per_turn=args.max_tokens,
        temperature=args.temperature,
    )

    print(f"\nTask:\n  {args.task}\n")
    print(f"Running agent loop (max {args.max_turns} turns)…\n")
    summary = await loop.run()

    print(f"--- Agent session {summary['session_id']} ---")
    for action in summary["actions"]:
        flag = "✓" if action.get("ok") else "✗"
        line = f"  turn {action.get('turn'):>2}  {flag}  {action.get('tool') or '<malformed>':>26}"
        if action.get("summary"):
            line += f"  {action['summary'][:80]}"
        if action.get("error"):
            line += f"  [error: {action['error'][:60]}]"
        print(line)

    print(f"\nTurns used: {summary['turns_used']}")
    print(f"Done summary: {summary['done_summary']}")
    print(f"\nFinal store stats: {summary['store_stats']}")
    return 0 if summary.get("done_summary") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
