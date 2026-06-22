"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

// Mirrors the FastAPI Subject / SubjectVersion shape used by /agent.
// Duplicated rather than imported to keep this route a self-contained
// dashboard — coupling it to /agent's internals would defeat the point
// of promoting it out of that page.
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
  triggered_by: "manual" | "schedule" | "agent" | "migration";
  status: "pending" | "running" | "completed" | "failed";
  started_at: string;
  ended_at: string | null;
  rationale: string;
  change_summary: SubjectVersionChangeSummary | null;
};

type SubjectListRow = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
  version_count: number;
  latest_version: SubjectVersion | null;
};

type StatsResponse = {
  entities: number;
  relations: number;
  kinds: number;
  facets: number;
  tickers: number;
  snapshot_version: number;
};

function formatRelative(iso: string | null, locale: Locale): string {
  if (!iso) return locale === "zh" ? "尚未运行" : "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = (Date.now() - t) / 1000;
  const units: [number, string, string][] = [
    [86400, "天", "d"],
    [3600, "小时", "h"],
    [60, "分钟", "m"],
    [1, "秒", "s"],
  ];
  for (const [s, zh, en] of units) {
    if (delta >= s) {
      const n = Math.floor(delta / s);
      return locale === "zh" ? `${n}${zh}前` : `${n}${en} ago`;
    }
  }
  return locale === "zh" ? "刚刚" : "just now";
}

export default function OverviewPage() {
  const [subjects, setSubjects] = useState<SubjectListRow[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [sRes, stRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/industry_graph/subjects`, { cache: "no-store" }),
          fetch(`${API_URL}/api/v1/industry_graph/stats`, { cache: "no-store" }),
        ]);
        if (!sRes.ok) throw new Error(`subjects ${sRes.status}`);
        if (!stRes.ok) throw new Error(`stats ${stRes.status}`);
        const d: { subjects: SubjectListRow[] } = await sRes.json();
        const stat: StatsResponse = await stRes.json();
        if (cancelled) return;
        setSubjects(d.subjects);
        setStats(stat);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const totals = {
    company: subjects.filter((s) => s.type === "company").length,
    theme: subjects.filter((s) => s.type === "theme").length,
  };

  const overviewCounts = useMemo(() => {
    const versions = subjects.reduce((acc, s) => acc + (s.version_count || 0), 0);
    const completed = subjects.filter(
      (s) => s.latest_version?.status === "completed",
    ).length;
    const failed = subjects.filter(
      (s) => s.latest_version?.status === "failed",
    ).length;
    const dayAgo = Date.now() - 86400 * 1000;
    const today = subjects.filter((s) => {
      const t = s.latest_version?.ended_at;
      return t ? new Date(t).getTime() >= dayAgo : false;
    }).length;
    return { versions, completed, failed, today };
  }, [subjects]);

  const inFlight = useMemo(
    () =>
      subjects.filter(
        (s) =>
          s.latest_version?.status === "running" ||
          s.latest_version?.status === "pending",
      ),
    [subjects],
  );

  const recentTop = useMemo(() => {
    const rows = subjects
      .filter((s) => s.latest_version)
      .map((s) => ({ subject: s, version: s.latest_version! }));
    rows.sort((a, b) => {
      const at = a.version.ended_at ?? a.version.started_at;
      const bt = b.version.ended_at ?? b.version.started_at;
      return new Date(bt).getTime() - new Date(at).getTime();
    });
    return rows.slice(0, 8);
  }, [subjects]);

  const agentStatus: "idle" | "running" = inFlight.length > 0 ? "running" : "idle";

  return (
    <PortalShell
      active="overview"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "概览" : "Overview"}
      subtitle={
        isZh
          ? "Agent 当前在跑什么 · Subject 覆盖 · 最近活动一眼看完。"
          : "What the agent is doing right now, coverage of Subjects, and recent activity at a glance."
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="agent-page">
        <section className="agent-kpis">
          <div className={`agent-kpi status-${agentStatus}`}>
            <div className="agent-kpi-eyebrow">
              {isZh ? "状态" : "Status"}
            </div>
            <div className="agent-kpi-big">
              <span className={`agent-status-dot ${agentStatus}`} />
              {agentStatus === "running"
                ? isZh
                  ? "运行中"
                  : "Running"
                : isZh
                  ? "空闲"
                  : "Idle"}
            </div>
            <div className="agent-kpi-foot">
              {inFlight.length > 0
                ? isZh
                  ? `${inFlight.length} 个 Subject 跑分析中`
                  : `${inFlight.length} subject(s) analyzing`
                : isZh
                  ? "Agent 在等任务"
                  : "Idle — waiting for work"}
            </div>
          </div>

          <div className="agent-kpi-row">
            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "Subjects" : "Subjects"}
              </div>
              <div className="agent-kpi-big">{subjects.length}</div>
              <div className="agent-kpi-foot">
                {isZh
                  ? `${totals.company} 公司 · ${totals.theme} 主题`
                  : `${totals.company} co · ${totals.theme} th`}
              </div>
            </div>

            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "Versions" : "Versions"}
              </div>
              <div className="agent-kpi-big">{overviewCounts.versions}</div>
              <div className="agent-kpi-foot">
                {isZh
                  ? `${overviewCounts.completed} 完成 · ${overviewCounts.failed} 失败 · ${overviewCounts.today} 24h 内`
                  : `${overviewCounts.completed} done · ${overviewCounts.failed} failed · ${overviewCounts.today} in 24h`}
              </div>
            </div>

            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "Store" : "Store"}
              </div>
              <div className="agent-kpi-big">{stats?.entities ?? "—"}</div>
              <div className="agent-kpi-foot">
                {stats
                  ? isZh
                    ? `${stats.relations} 关系 · v${stats.snapshot_version} · ${stats.tickers} ticker`
                    : `${stats.relations} rel · v${stats.snapshot_version} · ${stats.tickers} tickers`
                  : ""}
              </div>
            </div>
          </div>
        </section>

        <section className="agent-section">
          <header className="agent-section-head">
            <h2>{isZh ? "进行中 · In flight" : "In flight"}</h2>
          </header>
          {inFlight.length === 0 ? (
            <p className="muted">
              {isZh
                ? "目前没有 SubjectVersion 在跑。打开一个 Subject → 「+ 新分析」可以触发一次。"
                : "Nothing analyzing right now. Open a Subject and press '+ Run new' to start."}
            </p>
          ) : (
            <ul className="agent-flight-list">
              {inFlight.map((s) => (
                <li key={s.id} className="agent-flight">
                  <span className="agent-pulse" aria-hidden />
                  <Link
                    href={`/agent/${encodeURIComponent(s.id)}`}
                    className="agent-flight-name"
                  >
                    {s.display_name}
                  </Link>
                  <span className="agent-flight-meta">
                    v{s.latest_version!.version_no} ·{" "}
                    {s.latest_version!.triggered_by} ·{" "}
                    {formatRelative(s.latest_version!.started_at, locale)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="agent-section">
          <header className="agent-section-head">
            <h2>{isZh ? "最近活动 · Recent" : "Recent activity"}</h2>
            <Link href="/agent?view=activity" className="live-pill">
              {isZh ? "全部 →" : "All →"}
            </Link>
          </header>
          {recentTop.length === 0 ? (
            <p className="muted">
              {isZh ? "尚无活动记录。" : "No activity yet."}
            </p>
          ) : (
            <ul className="agent-recent-list">
              {recentTop.map(({ subject, version }) => (
                <li key={version.id} className="agent-recent">
                  <Link
                    href={`/agent/${encodeURIComponent(subject.id)}`}
                    className="agent-recent-link"
                  >
                    <span className="agent-recent-name">{subject.display_name}</span>
                    <span className="agent-recent-meta">
                      v{version.version_no} · {version.triggered_by} ·{" "}
                      {formatRelative(version.ended_at ?? version.started_at, locale)}
                    </span>
                    {version.change_summary ? (
                      <span className="agent-recent-diff">
                        {version.change_summary.entities_added > 0
                          ? `+${version.change_summary.entities_added} ent`
                          : ""}
                        {version.change_summary.entities_added > 0 &&
                        version.change_summary.relations_added > 0
                          ? " · "
                          : ""}
                        {version.change_summary.relations_added > 0
                          ? `+${version.change_summary.relations_added} rel`
                          : ""}
                      </span>
                    ) : version.triggered_by === "migration" ? (
                      <span className="agent-recent-diff muted">
                        {isZh ? "基线" : "baseline"}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </PortalShell>
  );
}
