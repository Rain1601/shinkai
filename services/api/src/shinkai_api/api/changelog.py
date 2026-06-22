"""Changelog endpoint — serve the CHANGELOG.md as structured JSON.

We parse the markdown server-side rather than shipping it to the web
and parsing in the browser: the format is stable, the file is small
(~12 KB), the parser is simpler than a Markdown-AST library, and we
can apply consistent grouping + sorting without leaking renderer state
into the UI.

Shape returned to the web:

  {
    "entries": [
      {
        "date_range": "2026-06-21 → 06-22",  # or "2026-06-22"
        "title": "Run-centric reframe",
        "sections": [
          {
            "type": "milestone",            # or feature/ui/fix/...
            "heading": "/agent becomes the home screen",
            "body_md": "...",               # narrative paragraph(s)
            "commits": [
              {"hash": "f2e4ee1", "message": "feat(web): promote Overview ..."},
              ...
            ]
          }
        ]
      },
      ...
    ],
    "source": "CHANGELOG.md",
    "source_mtime_ms": 1718950000000
  }
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/changelog", tags=["changelog"])

# CHANGELOG.md lives at the repo root. parents path:
#   [0] api/  [1] shinkai_api/  [2] src/  [3] api/  [4] services/  [5] repo_root
_REPO_ROOT = Path(__file__).resolve().parents[5]
_CHANGELOG_PATH = _REPO_ROOT / "CHANGELOG.md"

# Matches `## 2026-06-21`, `## 2026-06-21 · Some title`, or `## 2026-06-21 → 06-22 · Title`
_H2_RE = re.compile(
    r"^##\s+(?P<date>\d{4}-\d{2}-\d{2}(?:\s*→\s*\d{2}-\d{2})?)"
    r"(?:\s*[·•\-]\s*(?P<title>.+?))?\s*$"
)
# Matches `### [type] Heading`
_H3_RE = re.compile(r"^###\s+\[(?P<type>[a-z_]+)\]\s+(?P<heading>.+?)\s*$")
# Matches `- ` `abc1234` ` message text`  (markdown bullet + inline code hash)
_COMMIT_RE = re.compile(r"^[-*]\s+`(?P<hash>[0-9a-f]{6,40})`\s+(?P<message>.+?)\s*$")


@dataclass
class _Section:
    type: str
    heading: str
    body_lines: list[str]
    commits: list[dict[str, str]]


@dataclass
class _Entry:
    date_range: str
    title: str
    sections: list[_Section]


def _parse(text: str) -> list[_Entry]:
    """Walk the markdown line-by-line into entries + sections.

    The parser is forgiving: any line that doesn't match an H2/H3/commit
    bullet falls into the current section's body. Lines before the first
    H2 (the file preamble) are silently skipped.
    """
    entries: list[_Entry] = []
    current_entry: _Entry | None = None
    current_section: _Section | None = None

    def _close_section() -> None:
        if current_section and current_entry is not None:
            current_entry.sections.append(current_section)

    for raw in text.splitlines():
        line = raw.rstrip()

        h2 = _H2_RE.match(line)
        if h2:
            _close_section()
            current_section = None
            current_entry = _Entry(
                date_range=h2.group("date").strip(),
                title=(h2.group("title") or "").strip(),
                sections=[],
            )
            entries.append(current_entry)
            continue

        if current_entry is None:
            continue  # preamble

        h3 = _H3_RE.match(line)
        if h3:
            _close_section()
            current_section = _Section(
                type=h3.group("type"),
                heading=h3.group("heading").strip(),
                body_lines=[],
                commits=[],
            )
            continue

        if current_section is None:
            continue

        commit = _COMMIT_RE.match(line)
        if commit:
            current_section.commits.append(
                {"hash": commit.group("hash"), "message": commit.group("message").strip()}
            )
            continue

        current_section.body_lines.append(raw)

    _close_section()
    return entries


def _entry_to_dict(entry: _Entry) -> dict[str, Any]:
    return {
        "date_range": entry.date_range,
        "title": entry.title,
        "sections": [
            {
                "type": s.type,
                "heading": s.heading,
                "body_md": "\n".join(s.body_lines).strip(),
                "commits": s.commits,
            }
            for s in entry.sections
        ],
    }


@router.get("")
async def get_changelog() -> dict[str, Any]:
    if not _CHANGELOG_PATH.exists():
        raise HTTPException(status_code=404, detail="CHANGELOG.md not found")
    text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    entries = _parse(text)
    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "source": "CHANGELOG.md",
        "source_mtime_ms": int(_CHANGELOG_PATH.stat().st_mtime * 1000),
    }
