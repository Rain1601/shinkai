"use client";

import { useEffect, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

// Mirrors the FastAPI changelog endpoint payload shape.
type ChangelogCommit = {
  hash: string;
  message: string;
};

type ChangelogSection = {
  type: string;
  heading: string;
  body_md: string;
  commits: ChangelogCommit[];
};

type ChangelogEntry = {
  date_range: string;
  title: string;
  sections: ChangelogSection[];
};

type ChangelogPayload = {
  entries: ChangelogEntry[];
  source: string;
  source_mtime_ms: number;
};

const TYPE_LABELS_ZH: Record<string, string> = {
  milestone: "里程碑",
  integration: "接入",
  feature: "新能力",
  ui: "界面",
  design: "设计",
  fix: "修复",
  docs: "文档",
  decision: "决策",
};

// Strip the inline preamble dashes / blank-line separators the parser
// captured along with body text — keeps the rendered cards tidy.
function tidyBody(md: string): string {
  return md
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && line !== "---")
    .join("\n\n");
}

export default function TimelinePage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [data, setData] = useState<ChangelogPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const isZh = locale === "zh";

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/v1/changelog`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ChangelogPayload>;
      })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function changeLocale(next: Locale) {
    setLocale(next);
    window.localStorage.setItem("shinkai.locale", next);
  }

  // Tally section types so the filter chips show counts.
  const typeCounts = new Map<string, number>();
  let totalSections = 0;
  let totalCommits = 0;
  if (data) {
    for (const entry of data.entries) {
      for (const s of entry.sections) {
        typeCounts.set(s.type, (typeCounts.get(s.type) ?? 0) + 1);
        totalSections += 1;
        totalCommits += s.commits.length;
      }
    }
  }
  const allTypes = Array.from(typeCounts.entries()).sort((a, b) => b[1] - a[1]);

  return (
    <PortalShell
      active="timeline"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "演化时间线" : "Evolution Timeline"}
      subtitle={
        isZh
          ? `shinkai 自 2026-05-31 day 0 起的里程碑与更新轨迹 · 来自 ${data?.source ?? "CHANGELOG.md"}`
          : `Milestones + updates since day 0 (2026-05-31) · sourced from ${data?.source ?? "CHANGELOG.md"}`
      }
    >
      {error ? (
        <div className="timeline-error">
          {isZh ? "无法加载时间线:" : "Failed to load timeline:"} {error}
        </div>
      ) : !data ? (
        <div className="timeline-loading">
          {isZh ? "加载中…" : "Loading…"}
        </div>
      ) : (
        <>
          <section className="timeline-summary">
            <div className="timeline-summary-stat">
              <span className="timeline-summary-num">{data.entries.length}</span>
              <span className="timeline-summary-lab">
                {isZh ? "时间节点" : "entries"}
              </span>
            </div>
            <div className="timeline-summary-stat">
              <span className="timeline-summary-num">{totalSections}</span>
              <span className="timeline-summary-lab">
                {isZh ? "条目" : "sections"}
              </span>
            </div>
            <div className="timeline-summary-stat">
              <span className="timeline-summary-num">{totalCommits}</span>
              <span className="timeline-summary-lab">
                {isZh ? "提交" : "commits"}
              </span>
            </div>
          </section>

          <nav
            className="timeline-filter"
            aria-label={isZh ? "类型过滤" : "Type filter"}
          >
            <button
              type="button"
              className={`timeline-filter-chip ${
                activeFilter === "all" ? "active" : ""
              }`}
              onClick={() => setActiveFilter("all")}
            >
              {isZh ? "全部" : "All"} · {totalSections}
            </button>
            {allTypes.map(([t, n]) => (
              <button
                key={t}
                type="button"
                className={`timeline-filter-chip type-${t} ${
                  activeFilter === t ? "active" : ""
                }`}
                onClick={() => setActiveFilter(t)}
              >
                {isZh ? TYPE_LABELS_ZH[t] ?? t : t} · {n}
              </button>
            ))}
          </nav>

          <ol className="timeline-feed">
            {data.entries.map((entry, entryIdx) => {
              const visibleSections =
                activeFilter === "all"
                  ? entry.sections
                  : entry.sections.filter((s) => s.type === activeFilter);
              if (visibleSections.length === 0) return null;
              const isFirstMonth =
                entryIdx === 0 ||
                entry.date_range.slice(0, 7) !==
                  data.entries[entryIdx - 1].date_range.slice(0, 7);
              return (
                <li key={entry.date_range + entryIdx} className="timeline-entry">
                  {isFirstMonth && (
                    <div className="timeline-month-tag">
                      {entry.date_range.slice(0, 7)}
                    </div>
                  )}
                  <div className="timeline-entry-rail" aria-hidden="true" />
                  <header className="timeline-entry-head">
                    <span className="timeline-entry-date">{entry.date_range}</span>
                    {entry.title && (
                      <h2 className="timeline-entry-title">{entry.title}</h2>
                    )}
                  </header>
                  <div className="timeline-entry-sections">
                    {visibleSections.map((s, i) => (
                      <article
                        key={s.heading + i}
                        className={`timeline-section type-${s.type}`}
                      >
                        <header className="timeline-section-head">
                          <span
                            className={`timeline-section-tag type-${s.type}`}
                          >
                            {isZh ? TYPE_LABELS_ZH[s.type] ?? s.type : s.type}
                          </span>
                          <h3 className="timeline-section-heading">{s.heading}</h3>
                        </header>
                        {s.body_md && (
                          <p className="timeline-section-body">
                            {tidyBody(s.body_md)}
                          </p>
                        )}
                        {s.commits.length > 0 && (
                          <details className="timeline-commits">
                            <summary>
                              {isZh
                                ? `${s.commits.length} 个 commit`
                                : `${s.commits.length} commit${
                                    s.commits.length === 1 ? "" : "s"
                                  }`}
                            </summary>
                            <ul>
                              {s.commits.map((c) => (
                                <li key={c.hash}>
                                  <code className="timeline-commit-hash">
                                    {c.hash.slice(0, 7)}
                                  </code>
                                  <span className="timeline-commit-msg">
                                    {c.message}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                      </article>
                    ))}
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </PortalShell>
  );
}
