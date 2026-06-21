"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type Stats = {
  entities: number;
  relations: number;
  kinds: number;
  facets: number;
  tickers: number;
  snapshot_version: number;
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
  change_summary: {
    entities_added: number;
    relations_added: number;
    highlights: string[];
  } | null;
};

type SubjectListRow = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
  version_count: number;
  latest_version: SubjectVersion | null;
};

function formatRelative(iso: string | null, locale: Locale): string {
  if (!iso) return locale === "zh" ? "—" : "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = (Date.now() - t) / 1000;
  if (delta < 60) return locale === "zh" ? "刚刚" : "just now";
  const units: [number, string, string][] = [
    [86400, "天", "d"],
    [3600, "小时", "h"],
    [60, "分钟", "m"],
  ];
  for (const [s, zh, en] of units) {
    if (delta >= s) {
      const n = Math.floor(delta / s);
      return locale === "zh" ? `${n}${zh}前` : `${n}${en} ago`;
    }
  }
  return locale === "zh" ? "刚刚" : "just now";
}

export default function AgentOverviewPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [subjects, setSubjects] = useState<SubjectListRow[]>([]);
  const [loading, setLoading] = useState(true);
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
        const [s, ss] = await Promise.all([
          fetch(`${API_URL}/api/v1/industry_graph/stats`, { cache: "no-store" }),
          fetch(`${API_URL}/api/v1/industry_graph/subjects`, { cache: "no-store" }),
        ]);
        if (!s.ok) throw new Error(`stats ${s.status}`);
        if (!ss.ok) throw new Error(`subjects ${ss.status}`);
        const statsData: Stats = await s.json();
        const subjectsData: { subjects: SubjectListRow[] } = await ss.json();
        if (cancelled) return;
        setStats(statsData);
        setSubjects(subjectsData.subjects);
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

  // Derived stats — all from the two fetches; no extra endpoints needed.
  const counts = useMemo(() => {
    const company = subjects.filter((s) => s.type === "company").length;
    const theme = subjects.filter((s) => s.type === "theme").length;
    const versions = subjects.reduce((acc, s) => acc + (s.version_count || 0), 0);
    const completed = subjects.filter(
      (s) => s.latest_version?.status === "completed",
    ).length;
    const running = subjects.filter(
      (s) => s.latest_version?.status === "running" || s.latest_version?.status === "pending",
    ).length;
    const failed = subjects.filter(
      (s) => s.latest_version?.status === "failed",
    ).length;
    const dayAgo = Date.now() - 86400 * 1000;
    const today = subjects.filter((s) => {
      const t = s.latest_version?.ended_at;
      return t ? new Date(t).getTime() >= dayAgo : false;
    }).length;
    return { company, theme, versions, completed, running, failed, today };
  }, [subjects]);

  const inFlight = useMemo(
    () =>
      subjects.filter(
        (s) => s.latest_version?.status === "running" || s.latest_version?.status === "pending",
      ),
    [subjects],
  );

  const recent = useMemo(() => {
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

  const status: "idle" | "running" = inFlight.length > 0 ? "running" : "idle";

  return (
    <PortalShell
      active="agent"
      locale={locale}
      onLocaleChange={changeLocale}
      title="shinkai · 深海"
      subtitle={
        isZh
          ? "持续研究引擎 · Subject 维度的总览"
          : "Continuous research engine · Subject-centric overview"
      }
      actions={
        <Link href="/industry-graph" className="live-pill">
          {isZh ? "打开产业图谱 →" : "Open Industry Graph →"}
        </Link>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      {loading ? (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      ) : (
        <div className="agent-page">
          {/* ─ KPI strip ─ */}
          <section className="agent-kpis">
            <div className={`agent-kpi status-${status}`}>
              <div className="agent-kpi-eyebrow">
                {isZh ? "状态 · STATUS" : "Status"}
              </div>
              <div className="agent-kpi-big">
                <span className={`agent-status-dot ${status}`} />
                {status === "running"
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
                    ? "无 SubjectVersion 在跑"
                    : "no active SubjectVersion"}
              </div>
            </div>

            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "Subjects · 追踪中" : "Subjects · tracked"}
              </div>
              <div className="agent-kpi-big">{subjects.length}</div>
              <div className="agent-kpi-foot">
                {isZh
                  ? `${counts.company} 公司 · ${counts.theme} 主题`
                  : `${counts.company} co · ${counts.theme} th`}
              </div>
            </div>

            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "SubjectVersions · 累计" : "Versions · lifetime"}
              </div>
              <div className="agent-kpi-big">{counts.versions}</div>
              <div className="agent-kpi-foot">
                {isZh
                  ? `${counts.completed} 完成 · ${counts.failed} 失败 · ${counts.today} 24h 内`
                  : `${counts.completed} done · ${counts.failed} failed · ${counts.today} in 24h`}
              </div>
            </div>

            <div className="agent-kpi">
              <div className="agent-kpi-eyebrow">
                {isZh ? "图谱 · 覆盖" : "Store · coverage"}
              </div>
              <div className="agent-kpi-big">{stats?.entities ?? "—"}</div>
              <div className="agent-kpi-foot">
                {stats
                  ? isZh
                    ? `${stats.relations} 关系 · v${stats.snapshot_version} · ${stats.tickers} ticker`
                    : `${stats.relations} relations · v${stats.snapshot_version} · ${stats.tickers} tickers`
                  : ""}
              </div>
            </div>
          </section>

          {/* ─ In flight ─ */}
          <section className="agent-section">
            <header className="agent-section-head">
              <h2>{isZh ? "进行中 · In flight" : "In flight"}</h2>
            </header>
            {inFlight.length === 0 ? (
              <p className="muted">
                {isZh
                  ? "目前没有 SubjectVersion 在跑。在 Industry Graph 中选一个 Subject → 「+ 新分析」可以触发一次。"
                  : "Nothing analyzing right now. Pick a Subject in Industry Graph and press \"+ Run new\" to start."}
              </p>
            ) : (
              <ul className="agent-flight-list">
                {inFlight.map((s) => (
                  <li key={s.id} className="agent-flight">
                    <span className="agent-pulse" aria-hidden />
                    <Link
                      href={`/industry-graph/${encodeURIComponent(s.id)}`}
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

          {/* ─ Recent activity ─ */}
          <section className="agent-section">
            <header className="agent-section-head">
              <h2>{isZh ? "最近活动 · Recent" : "Recent activity"}</h2>
              <Link href="/industry-graph?view=activity" className="live-pill">
                {isZh ? "全部 →" : "All →"}
              </Link>
            </header>
            {recent.length === 0 ? (
              <p className="muted">
                {isZh ? "尚无活动记录。" : "No activity yet."}
              </p>
            ) : (
              <ul className="agent-recent-list">
                {recent.map(({ subject, version }) => (
                  <li key={version.id} className="agent-recent">
                    <Link
                      href={`/industry-graph/${encodeURIComponent(subject.id)}`}
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

          {/* ─ Footer CTA ─ */}
          <section className="agent-cta">
            <p>
              {isZh
                ? "继续研究 → 在产业图谱里选一个 Subject 深挖。"
                : "Continue research → pick a Subject in Industry Graph and dive in."}
            </p>
            <Link href="/industry-graph" className="ig-run-btn">
              {isZh ? "打开 Industry Graph" : "Open Industry Graph"}
            </Link>
          </section>
        </div>
      )}
    </PortalShell>
  );
}
