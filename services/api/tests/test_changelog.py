"""Tests for shinkai_api.api.changelog parser.

Endpoint correctness is covered by the runtime smoke (the real
CHANGELOG.md file gets served). These tests pin the parser against
hand-crafted markdown so a regression in the regexes surfaces here
before the live page breaks.
"""

from __future__ import annotations

import textwrap

from shinkai_api.api.changelog import _parse


def test_parse_single_entry_single_section() -> None:
    md = textwrap.dedent(
        """\
        # Shinkai Changelog

        preamble we ignore

        ---

        ## 2026-06-22

        ### [ui] Overview KPI tighten

        Status card keeps full-width hero treatment.

        - `da7ee27` ui(web): tighten Overview KPIs — status hero + 3-up row
        """
    )
    entries = _parse(md)
    assert len(entries) == 1
    e = entries[0]
    assert e.date_range == "2026-06-22"
    assert e.title == ""
    assert len(e.sections) == 1
    s = e.sections[0]
    assert s.type == "ui"
    assert s.heading == "Overview KPI tighten"
    assert "full-width hero" in "\n".join(s.body_lines)
    assert s.commits == [
        {
            "hash": "da7ee27",
            "message": "ui(web): tighten Overview KPIs — status hero + 3-up row",
        }
    ]


def test_parse_date_range_with_title() -> None:
    md = textwrap.dedent(
        """\
        ## 2026-06-21 → 06-22 · Run-centric reframe

        ### [milestone] /agent becomes the home screen

        Body.

        - `f2e4ee1` feat(web): promote Overview
        - `f0b2905` feat(web): Stage 7 — SubjectVersion detail
        """
    )
    entries = _parse(md)
    assert len(entries) == 1
    assert entries[0].date_range == "2026-06-21 → 06-22"
    assert entries[0].title == "Run-centric reframe"
    assert len(entries[0].sections[0].commits) == 2


def test_parse_multiple_sections_in_one_entry() -> None:
    md = textwrap.dedent(
        """\
        ## 2026-06-21 · Industry Graph V0

        ### [milestone] V0 ships

        First section body.

        - `f049367` feat(api): industry_graph V0

        ### [feature] Theme + cross-subject merge

        Second section body.

        - `4cb1b36` feat: Stage 1
        - `f6610f0` feat: Stage 2
        """
    )
    entries = _parse(md)
    assert len(entries) == 1
    sections = entries[0].sections
    assert len(sections) == 2
    assert sections[0].type == "milestone"
    assert sections[1].type == "feature"
    assert len(sections[0].commits) == 1
    assert len(sections[1].commits) == 2


def test_parse_skips_preamble_lines_before_first_h2() -> None:
    md = textwrap.dedent(
        """\
        # Title

        Some intro paragraph.

        - `aaa` should not become a commit because there's no entry yet
        - `bbb` also ignored

        ### [milestone] also ignored — outside any entry

        ## 2026-06-01

        ### [feature] valid section
        """
    )
    entries = _parse(md)
    assert len(entries) == 1
    assert entries[0].sections[0].type == "feature"
    assert entries[0].sections[0].commits == []


def test_parse_handles_real_changelog_file() -> None:
    """Smoke: the actual CHANGELOG.md in the repo parses without crash."""
    from shinkai_api.api.changelog import _CHANGELOG_PATH

    if not _CHANGELOG_PATH.exists():
        return  # skip when run from an unusual cwd
    entries = _parse(_CHANGELOG_PATH.read_text(encoding="utf-8"))
    assert len(entries) >= 5
    # Every section should have a type + heading; commits may be empty.
    for e in entries:
        for s in e.sections:
            assert s.type
            assert s.heading
