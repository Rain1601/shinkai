"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ActivityFeed } from "../../components/industry-graph/ActivityFeed";
import { PortalShell } from "../../components/portal/PortalShell";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

// Mirrors the FastAPI Subject / SubjectVersion shape.
type SubjectVersionChangeSummary = {
  entities_added: number;
  entities_updated: number;
  entities_deprecated: number;
  relations_added: number;
  relations_updated: number;
  relations_deprecated: number;
  highlights: string[];
};

type SubjectVersion = {
  id: string;
  subject_id: string;
  version_no: number;
  run_id: string;
  snapshot_from: number;
  snapshot_to: number;
  triggered_by: "manual" | "schedule" | "agent" | "migration";
  status: "pending" | "running" | "completed" | "failed";
  started_at: string;
  ended_at: string | null;
  scope_node_ids: string[];
  rationale: string;
  change_summary: SubjectVersionChangeSummary | null;
};

type SubjectListRow = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
  schedule: { cron: string | null; autonomous: boolean };
  created_at: string;
  updated_at: string;
  version_count: number;
  latest_version: SubjectVersion | null;
};

type ListResponse = { subjects: SubjectListRow[] };

type ThemeEvent = {
  event_id: string;
  theme_id: string;
  category: string;
  event_ts: number;
  title: string;
  summary: string;
  key_facts: string[];
  tickers: string[];
  source: {
    url: string;
    title: string;
    publisher: string;
    tier: string;
    reliability: number;
  };
  relevance: number;
};

type SubjectEventsResponse = { subject_id: string; events: ThemeEvent[]; count: number };

type SubjectType = "all" | "company" | "theme";

function formatRelative(iso: string | null, locale: Locale): string {
  if (!iso) return locale === "zh" ? "尚未运行" : "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = (Date.now() - t) / 1000;
  const abs = Math.abs(delta);
  const units: [number, string, string][] = [
    [86400, "天", "d"],
    [3600, "小时", "h"],
    [60, "分钟", "m"],
    [1, "秒", "s"],
  ];
  for (const [s, zh, en] of units) {
    if (abs >= s) {
      const n = Math.floor(abs / s);
      return locale === "zh" ? `${n}${zh}前` : `${n}${en} ago`;
    }
  }
  return locale === "zh" ? "刚刚" : "just now";
}

function formatEventDate(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toISOString().slice(0, 10);
}

function categoryLabel(c: string, locale: Locale): string {
  const zh: Record<string, string> = {
    earnings: "财报",
    m_and_a: "并购",
    product: "产品",
    regulation: "监管",
    supply_shock: "供需",
    industry: "行业",
    macro: "宏观",
    other: "其它",
  };
  const en: Record<string, string> = {
    earnings: "earnings",
    m_and_a: "M&A",
    product: "product",
    regulation: "regulation",
    supply_shock: "supply",
    industry: "industry",
    macro: "macro",
    other: "other",
  };
  return (locale === "zh" ? zh : en)[c] ?? c;
}

type ViewMode = "subjects" | "activity";

export default function IndustryGraphListPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialView: ViewMode =
    searchParams.get("view") === "activity" ? "activity" : "subjects";
  const [view, setView] = useState<ViewMode>(initialView);
  const [subjects, setSubjects] = useState<SubjectListRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<SubjectType>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  function switchView(next: ViewMode) {
    setView(next);
    const params = new URLSearchParams(searchParams.toString());
    if (next === "subjects") params.delete("view");
    else params.set("view", next);
    const qs = params.toString();
    router.replace(qs ? `/agent?${qs}` : "/agent", { scroll: false });
  }
  const [events, setEvents] = useState<ThemeEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [selectedVersions, setSelectedVersions] = useState<SubjectVersion[]>([]);
  const [locale, setLocale] = useState<Locale>("zh");
  const isZh = locale === "zh";

  function changeLocale(next: Locale) {
    setLocale(next);
    try {
      window.localStorage.setItem("shinkai.locale", next);
    } catch {}
  }

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("shinkai.locale");
      if (stored === "zh" || stored === "en") setLocale(stored);
    } catch {}
  }, []);

  // Load subjects
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch(`${API_URL}/api/v1/industry_graph/subjects`, {
          cache: "no-store",
        });
        if (!r.ok) throw new Error(`subjects ${r.status}`);
        const d: ListResponse = await r.json();
        if (cancelled) return;
        setSubjects(d.subjects);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load events + full version history for the selected subject. We fan out
  // two fetches in parallel so the right rail can show every analysis pass
  // for this subject (not just the global latest-version slice).
  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      setSelectedVersions([]);
      return;
    }
    let cancelled = false;
    setLoadingEvents(true);
    async function load() {
      try {
        const [evRes, detailRes] = await Promise.all([
          fetch(
            `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(selectedId!)}/events`,
            { cache: "no-store" },
          ),
          fetch(
            `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(selectedId!)}`,
            { cache: "no-store" },
          ),
        ]);
        if (!evRes.ok) throw new Error(`events ${evRes.status}`);
        if (!detailRes.ok) throw new Error(`subject ${detailRes.status}`);
        const ev: SubjectEventsResponse = await evRes.json();
        const detail: { versions: SubjectVersion[] } = await detailRes.json();
        if (cancelled) return;
        setEvents(ev.events);
        setSelectedVersions(detail.versions);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      } finally {
        if (!cancelled) setLoadingEvents(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Pre-compute filtered list + the right-rail records
  const filteredSubjects = useMemo(() => {
    const q = search.trim().toLowerCase();
    return subjects.filter((s) => {
      if (typeFilter !== "all" && s.type !== typeFilter) return false;
      if (!q) return true;
      return (
        s.display_name.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q) ||
        s.target_entity_id.toLowerCase().includes(q)
      );
    });
  }, [subjects, typeFilter, search]);

  const recentRecords = useMemo(() => {
    const rows: Array<{ subject: SubjectListRow; version: SubjectVersion }> = [];
    if (selectedId) {
      // Scoped view: every analysis pass for the selected subject.
      const subj = subjects.find((s) => s.id === selectedId);
      if (subj) {
        for (const v of selectedVersions) {
          rows.push({ subject: subj, version: v });
        }
      }
    } else {
      // Global view: the most recent run across every subject.
      for (const s of subjects) {
        if (s.latest_version) rows.push({ subject: s, version: s.latest_version });
      }
    }
    rows.sort((a, b) => {
      const at = a.version.ended_at ?? a.version.started_at;
      const bt = b.version.ended_at ?? b.version.started_at;
      return new Date(bt).getTime() - new Date(at).getTime();
    });
    return rows.slice(0, 30);
  }, [subjects, selectedId, selectedVersions]);

  const selectedSubject = selectedId
    ? subjects.find((s) => s.id === selectedId) ?? null
    : null;

  const totals = {
    all: subjects.length,
    company: subjects.filter((s) => s.type === "company").length,
    theme: subjects.filter((s) => s.type === "theme").length,
  };
  const runningCount = subjects.filter(
    (s) => s.latest_version?.status === "running",
  ).length;

  const headerCounts = isZh
    ? `${subjects.length} subjects · ${totals.company} 公司 · ${totals.theme} 主题${
        runningCount ? ` · ${runningCount} 在跑` : ""
      }`
    : `${subjects.length} subjects · ${totals.company} companies · ${totals.theme} themes${
        runningCount ? ` · ${runningCount} live` : ""
      }`;

  return (
    <PortalShell
      active="industry"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "产业图谱" : "Industry Graph"}
      subtitle={
        isZh
          ? "左侧挑 subject,中间看相关事件,右侧翻最近的分析记录,点击打开 detail。"
          : "Pick a subject on the left, read related events in the middle, browse recent analyses on the right; click into detail."
      }
      actions={<span className="live-workspace-counts">{headerCounts}</span>}
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="ig-tabs">
        <button
          type="button"
          className={`ig-tab ${view === "subjects" ? "active" : ""}`}
          onClick={() => switchView("subjects")}
        >
          {isZh ? "Subjects" : "Subjects"}
          <span className="ig-tab-count">{subjects.length}</span>
        </button>
        <button
          type="button"
          className={`ig-tab ${view === "activity" ? "active" : ""}`}
          onClick={() => switchView("activity")}
        >
          {isZh ? "Activity" : "Activity"}
        </button>
      </div>

      {view === "activity" ? (
        <section className="ig-activity-tab">
          <header className="ig-activity-tab-head">
            <h2>{isZh ? "全部分析活动" : "All analytical activity"}</h2>
            <p className="muted">
              {isZh
                ? "Mode B / Mode A 历次跑过的 dossier / 深析 / 判断,按时间倒序。"
                : "Dossiers, deep analyses and judgments from past Mode B / Mode A runs, newest first."}
            </p>
          </header>
          <ActivityFeed
            locale={locale}
            limit={80}
            subjectLookup={
              new Map(
                subjects.map((s) => [
                  s.id,
                  { id: s.id, display_name: s.display_name, type: s.type },
                ]),
              )
            }
          />
        </section>
      ) : (
      <div className="live-workspace">
        <aside className="live-themes">
          <div className="live-themes-header">
            <span className="label">{isZh ? "研究 Subject" : "Subjects"}</span>
            <button
              type="button"
              className={`live-pill ${selectedId === null ? "active" : ""}`}
              onClick={() => setSelectedId(null)}
            >
              {isZh ? "全部" : "All"}
            </button>
          </div>

          <div className="ig-pill-row">
            {(["all", "company", "theme"] as SubjectType[]).map((t) => (
              <button
                type="button"
                key={t}
                className={`live-pill ${typeFilter === t ? "active" : ""}`}
                onClick={() => setTypeFilter(t)}
              >
                {t === "all"
                  ? isZh
                    ? "全部"
                    : "All"
                  : t === "company"
                    ? isZh
                      ? "公司"
                      : "Company"
                    : isZh
                      ? "主题"
                      : "Theme"}
                <span className="ig-pill-count">{totals[t]}</span>
              </button>
            ))}
          </div>

          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="live-search"
            placeholder={isZh ? "搜索 subject…" : "Search subjects…"}
            spellCheck={false}
          />

          {loading ? (
            <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>
          ) : filteredSubjects.length === 0 ? (
            <p className="muted live-empty">
              {isZh ? "没有匹配的 subject。" : "No matching subjects."}
            </p>
          ) : (
            <ul className="live-theme-list">
              {filteredSubjects.map((s) => {
                const lv = s.latest_version;
                const running = lv?.status === "running";
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(s.id)}
                      className={`live-theme-row ${selectedId === s.id ? "active" : ""}`}
                    >
                      <div className="live-theme-row-title">
                        {running ? <span className="live-pulse" aria-hidden /> : null}
                        <span>{s.display_name}</span>
                      </div>
                      <div className="live-theme-row-meta">
                        <span>
                          {s.type === "company"
                            ? isZh
                              ? "公司"
                              : "company"
                            : isZh
                              ? "主题"
                              : "theme"}
                        </span>
                        <span>v{s.version_count}</span>
                        <span>{formatRelative(lv?.ended_at ?? lv?.started_at ?? null, locale)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        <section className="live-trace">
          <header className="live-trace-header">
            <h3>
              {selectedSubject
                ? selectedSubject.display_name + (isZh ? " · 事件" : " · events")
                : isZh
                  ? "全部 subject · 选一个查看事件"
                  : "All subjects · pick one to see events"}
            </h3>
            <div className="live-trace-header-meta">
              {selectedSubject ? (
                <Link
                  href={`/agent/${encodeURIComponent(selectedSubject.id)}`}
                  className="live-pill"
                >
                  {isZh ? "打开 detail →" : "open detail →"}
                </Link>
              ) : null}
            </div>
          </header>

          {!selectedSubject ? (
            <p className="muted live-empty" style={{ marginTop: 40 }}>
              {isZh ? "左侧选一个 subject 才能加载事件。" : "Pick a subject on the left."}
            </p>
          ) : loadingEvents ? (
            <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>
          ) : events.length === 0 ? (
            <p className="muted live-empty">
              {isZh
                ? "暂无事件 — 主题事件还未通过 /themes refresh 拉取过,或这家公司在事件流中没出现。"
                : "No events — theme refresh hasn't run, or this company hasn't appeared in events."}
            </p>
          ) : (
            <ul className="live-event-list">
              {events.map((e) => (
                <li key={e.event_id} className="live-event">
                  <div className="live-event-button">
                    <div className="live-event-row1">
                      <span className={`live-event-cat live-event-cat-${e.category}`}>
                        {categoryLabel(e.category, locale)}
                      </span>
                      <span className="live-event-date">{formatEventDate(e.event_ts)}</span>
                      <span
                        className="live-event-publisher"
                        title={e.source.url}
                      >
                        {e.source.publisher || (isZh ? "未知" : "unknown")}
                      </span>
                      <span className={`live-event-tier live-event-tier-${e.source.tier}`}>
                        {e.source.tier}
                      </span>
                    </div>
                    <p className="live-event-title">{e.title}</p>
                    {e.summary ? <p className="live-event-summary">{e.summary}</p> : null}
                    {e.tickers.length > 0 ? (
                      <div className="live-detail-row" style={{ marginTop: 6 }}>
                        {e.tickers.map((t) => (
                          <span className="live-event-ticker" key={t}>
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="live-records">
          <header className="live-records-header">
            <span className="label">
              {isZh ? "分析记录" : "Analyses"}
              {selectedSubject ? (
                <span className="muted" style={{ marginLeft: 8, fontFamily: "var(--mono)" }}>
                  · {selectedSubject.display_name}
                </span>
              ) : null}
            </span>
            <span className="muted">{recentRecords.length}</span>
          </header>
          {recentRecords.length === 0 ? (
            <p className="muted live-empty">
              {isZh ? "尚未有分析记录。" : "No analyses yet."}
            </p>
          ) : (
            <ul className="live-record-list">
              {recentRecords.map(({ subject, version }) => {
                const highlights = version.change_summary?.highlights ?? [];
                return (
                  <li key={version.id} className="live-record">
                    <Link
                      href={`/agent/${encodeURIComponent(subject.id)}`}
                      className="live-record-button"
                    >
                      <div className="live-record-top">
                        <span className="live-record-kind">
                          v{version.version_no}
                        </span>
                        <span className="live-record-meta">
                          {version.triggered_by} ·{" "}
                          {formatRelative(version.ended_at ?? version.started_at, locale)}
                        </span>
                      </div>
                      <p className="live-record-title">{subject.display_name}</p>
                      {version.rationale ? (
                        <p className="live-record-body">{version.rationale}</p>
                      ) : null}
                      {highlights.length > 0 ? (
                        <ul className="ig-record-highlights">
                          {highlights.slice(0, 3).map((h, i) => (
                            <li key={i}>{h}</li>
                          ))}
                        </ul>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>
      </div>
      )}
    </PortalShell>
  );
}
