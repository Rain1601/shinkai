#!/usr/bin/env python3
"""Interactive fxbaogao explorer — phase 1 of the shinkai integration.

Goal of this script: let us *manually* drive search → triage → download
against the fxbaogao MCP API before wiring it into the autonomous
harness. Three weeks of usage here is intentionally cheaper than
flipping it on in the harness and burning the 300-PDF monthly quota by
accident.

Usage
-----
    export SHINKAI_FXBAOGAO_API_KEY=sk-...
    python scripts/fxbg_explore.py search "HBM 2026" --org 摩根士丹利 --org 野村
    python scripts/fxbg_explore.py paragraphs 5385254 --keyword 硅光
    python scripts/fxbg_explore.py url 5385254
    python scripts/fxbg_explore.py download 5385254 --out ~/ResearchGraph/fxbg_corpus

All four commands print human-readable summaries to stdout and exit
non-zero on tool error. The script does not depend on Claude Code or
on the shinkai HTTP service; it talks straight to api.fxbaogao.com.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure src/ is importable when running from repo root without install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "services" / "api" / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shinkai_api.tools.fxbg import (  # noqa: E402
    FxbgParagraphsTool,
    FxbgPdfUrlTool,
    FxbgSearchTool,
    download_pdf_from_url,
)

DEFAULT_OUT = Path.home() / "ResearchGraph" / "fxbg_corpus"


async def cmd_search(args: argparse.Namespace) -> int:
    tool = FxbgSearchTool()
    result = await tool.run(
        keywords=args.keywords,
        org_names=args.org or None,
        use_default_orgs=not args.all_orgs,
        min_pages=args.min_pages,
        start_time=args.since,
    )
    if not result.ok:
        print(f"[error] {result.error}", file=sys.stderr)
        return 2

    hits = result.data.get("hits") or []
    effective_orgs = result.data.get("effective_orgs") or "(all)"
    print(f"\n{result.summary}")
    print(f"  orgs={effective_orgs}  min_pages={result.data.get('min_pages')}\n")
    if not hits:
        print("(no hits after filter)")
        return 0
    for i, h in enumerate(hits[: args.limit], 1):
        title = (h.get("title") or "").replace("<em>", "").replace("</em>", "")
        org = h.get("orgName") or "-"
        pages = h.get("pageNum") or "?"
        date = h.get("pubTimeStr") or "-"
        rid = h.get("reportId") or "?"
        print(f"  {i:>2}. id={rid:<10} {date:>11} {pages:>3}p  [{org}]")
        print(f"      {title[:115]}")
        # Show first hit paragraph as preview when present
        paragraphs = h.get("paragraphs") or []
        if paragraphs and isinstance(paragraphs[0], dict):
            preview = (paragraphs[0].get("content") or "")[:150]
            preview = preview.replace("<em>", "").replace("</em>", "")
            print(f"      → {preview}")
    return 0


async def cmd_paragraphs(args: argparse.Namespace) -> int:
    tool = FxbgParagraphsTool()
    result = await tool.run(report_id=args.report_id, keyword=args.keyword)
    if not result.ok:
        print(f"[error] {result.error}", file=sys.stderr)
        return 2

    print(f"\n{result.summary}\n")
    body = result.data.get("paragraphs")
    if isinstance(body, list):
        for i, p in enumerate(body, 1):
            if isinstance(p, dict):
                page = p.get("pageNum", "?")
                content = (p.get("content") or "").replace("<em>", "").replace("</em>", "")
                print(f"  [p{page}] {content[:300]}")
            else:
                print(f"  {i}. {p}")
    else:
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
    return 0


async def cmd_url(args: argparse.Namespace) -> int:
    tool = FxbgPdfUrlTool()
    result = await tool.run(report_id=args.report_id)
    if not result.ok:
        print(f"[error] {result.error}", file=sys.stderr)
        return 2
    print(result.data.get("pdf_url", ""))
    return 0


async def cmd_download(args: argparse.Namespace) -> int:
    tool = FxbgPdfUrlTool()
    url_result = await tool.run(report_id=args.report_id)
    if not url_result.ok:
        print(f"[error] {url_result.error}", file=sys.stderr)
        return 2
    url = url_result.data.get("pdf_url") or ""
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / (args.filename or f"{args.report_id}.pdf")
    if dest.exists() and not args.overwrite:
        print(f"[skip] {dest} already exists (pass --overwrite to refetch)")
        return 0
    try:
        n = await download_pdf_from_url(url, str(dest))
    except Exception as exc:  # noqa: BLE001
        print(f"[error] download failed: {exc}", file=sys.stderr)
        return 3
    print(f"[ok] {dest} ({n // 1024} KB)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="fxbaogao MCP explorer (phase 1)")
    subs = p.add_subparsers(dest="command", required=True)

    s = subs.add_parser("search", help="search reports")
    s.add_argument("keywords")
    s.add_argument("--org", action="append", default=[],
                   help="repeatable issuer filter (overrides MS/GS/Nomura default)")
    s.add_argument("--all-orgs", action="store_true",
                   help="disable the MS/GS/Nomura default whitelist")
    s.add_argument("--min-pages", type=int, default=3,
                   help="drop hits with pageNum below this (default 3)")
    s.add_argument("--since", default="last3mon",
                   help="last7day|last1mon|last3mon|last1year (default last3mon)")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_search)

    pg = subs.add_parser("paragraphs", help="get hit-paragraphs for a report")
    pg.add_argument("report_id", type=int)
    pg.add_argument("--keyword", required=True)
    pg.set_defaults(func=cmd_paragraphs)

    u = subs.add_parser("url", help="issue signed PDF url (consumes 1 download)")
    u.add_argument("report_id", type=int)
    u.set_defaults(func=cmd_url)

    d = subs.add_parser("download", help="get url + stream PDF to disk")
    d.add_argument("report_id", type=int)
    d.add_argument("--out", default=str(DEFAULT_OUT))
    d.add_argument("--filename", default=None)
    d.add_argument("--overwrite", action="store_true")
    d.set_defaults(func=cmd_download)
    return p


def main() -> int:
    if not os.environ.get("SHINKAI_FXBAOGAO_API_KEY"):
        print(
            "[error] set SHINKAI_FXBAOGAO_API_KEY first\n"
            "  export SHINKAI_FXBAOGAO_API_KEY=sk-...",
            file=sys.stderr,
        )
        return 1
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
