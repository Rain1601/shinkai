"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type RunRow = {
  id: string;
  subject_id: string;
  subject_display_name: string;
  subject_type: "company" | "theme";
  target_entity_id: string;
  version_no: number;
  run_id: string;
  snapshot_from: number;
  snapshot_to: number;
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

type RunsResponse = {
  rows: RunRow[];
  count: number;
  total: number;
};

type SubjectListRow = {
  id: string;
  display_name: string;
  type: "company" | "theme";
};

type StatusFilter = "all" | "pending" | "running" | "completed" | "failed";

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

export default function RunsPage() {
  const [rows, setRows] = useState<RunRow[]>([]);
  const [subjects, setSubjects] = useState<SubjectListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subjectFilter, setSubjectFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
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
    setLoading(true);
    async function load() {
      try {
        const params = new URLSearchParams();
        params.set("limit", "120");
        if (subjectFilter) params.set("subject_id", subjectFilter);
        if (statusFilter !== "all") params.set("status", statusFilter);
        const [rRes, sRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/industry_graph/runs?${params}`, {
            cache: "no-store",
          }),
          fetch(`${API_URL}/api/v1/industry_graph/subjects`, {
            cache: "no-store",
          }),
        ]);
        if (!rRes.ok) throw new Error(`runs ${rRes.status}`);
        if (!sRes.ok) throw new Error(`subjects ${sRes.status}`);
        const runs: RunsResponse = await rRes.json();
        const subs: { subjects: SubjectListRow[] } = await sRes.json();
        if (cancelled) return;
        setRows(runs.rows);
        setSubjects(subs.subjects);
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
  }, [subjectFilter, statusFilter]);

  const counts = useMemo(() => {
    const running = rows.filter(
      (r) => r.status === "running" || r.status === "pending",
    ).length;
    const completed = rows.filter((r) => r.status === "completed").length;
    const failed = rows.filter((r) => r.status === "failed").length;
    return { running, completed, failed };
  }, [rows]);

  const STATUS_OPTIONS: StatusFilter[] = [
    "all",
    "running",
    "completed",
    "failed",
  ];

  return (
    <PortalShell
      active="history"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "运行日志 · Run log" : "Run log"}
      subtitle={
        isZh
          ? "Agent 历次跑过的 SubjectVersion,按时间倒序。"
          : "Every SubjectVersion the agent has produced, newest first."
      }
      actions={
        <Link href="/agent" className="live-pill">
          {isZh ? "← 返回工作区" : "← Workspace"}
        </Link>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="runs-toolbar">
        <div className="runs-toolbar-field">
          <label htmlFor="runs-subject-filter">
            {isZh ? "Subject" : "Subject"}
          </label>
          <select
            id="runs-subject-filter"
            value={subjectFilter}
            onChange={(e) => setSubjectFilter(e.target.value)}
          >
            <option value="">{isZh ? "全部" : "All"}</option>
            {[...subjects]
              .sort((a, b) => a.display_name.localeCompare(b.display_name))
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
          </select>
        </div>

        <div className="runs-toolbar-pills">
          {STATUS_OPTIONS.map((s) => (
            <button
              type="button"
              key={s}
              className={`live-pill ${statusFilter === s ? "active" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === "all"
                ? isZh
                  ? "全部"
                  : "All"
                : s === "running"
                  ? isZh
                    ? "运行中"
                    : "Running"
                  : s === "completed"
                    ? isZh
                      ? "完成"
                      : "Completed"
                    : isZh
                      ? "失败"
                      : "Failed"}
            </button>
          ))}
        </div>

        <div className="runs-toolbar-summary">
          {isZh
            ? `${rows.length} 条 · ${counts.running} 在跑 · ${counts.completed} 完成 · ${counts.failed} 失败`
            : `${rows.length} entries · ${counts.running} running · ${counts.completed} done · ${counts.failed} failed`}
        </div>
      </div>

      {loading ? (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      ) : rows.length === 0 ? (
        <p className="muted runs-empty">
          {isZh
            ? "Agent 还没跑过这种条件下的 SubjectVersion。打开一个 Subject → 「+ 新分析」可以触发一次。"
            : "No SubjectVersions match these filters. Open a Subject and press '+ Run new' to trigger one."}
        </p>
      ) : (
        <ul className="runs-list">
          {rows.map((r) => (
            <li key={r.id} className="runs-row">
              <Link href={`/runs/${encodeURIComponent(r.id)}`} className="runs-row-link">
                <span className={`runs-row-status status-${r.status}`}>
                  {r.status === "running" || r.status === "pending" ? (
                    <span className="runs-row-pulse" aria-hidden />
                  ) : null}
                  {r.status}
                </span>
                <span className="runs-row-version">v{r.version_no}</span>
                <span className="runs-row-subject">
                  {r.subject_display_name}
                  <span className={`runs-row-type type-${r.subject_type}`}>
                    {r.subject_type === "company"
                      ? isZh
                        ? "公司"
                        : "co"
                      : isZh
                        ? "主题"
                        : "th"}
                  </span>
                </span>
                <span className="runs-row-trigger">{r.triggered_by}</span>
                <span className="runs-row-time">
                  {formatRelative(r.ended_at ?? r.started_at, locale)}
                </span>
                <span className="runs-row-diff">
                  {r.change_summary ? (
                    <>
                      {r.change_summary.entities_added > 0
                        ? `+${r.change_summary.entities_added} ent`
                        : ""}
                      {r.change_summary.entities_added > 0 &&
                      r.change_summary.relations_added > 0
                        ? " · "
                        : ""}
                      {r.change_summary.relations_added > 0
                        ? `+${r.change_summary.relations_added} rel`
                        : ""}
                    </>
                  ) : r.triggered_by === "migration" ? (
                    <span className="muted">{isZh ? "基线" : "baseline"}</span>
                  ) : null}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PortalShell>
  );
}
