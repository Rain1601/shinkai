"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { PortalShell } from "../../../components/portal/PortalShell";
import { SubjectGraph } from "../../../components/industry-graph/SubjectGraph";
import type { GraphPayload } from "../../../components/industry-graph/cytoscape-helpers";
import { type Locale } from "../../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

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
  task_prompt?: string;
  error?: string | null;
};

type SubjectDetail = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
  schedule: { cron: string | null; autonomous: boolean };
  versions: SubjectVersion[];
};

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

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export default function IndustryGraphSubjectDetail({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}) {
  const { subjectId: rawId } = use(params);
  const subjectId = decodeURIComponent(rawId);

  const [subject, setSubject] = useState<SubjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
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

  const fetchSubject = useCallback(async () => {
    try {
      const r = await fetch(
        `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}`,
        { cache: "no-store" },
      );
      if (!r.ok) throw new Error(`subject ${r.status}`);
      const d: SubjectDetail = await r.json();
      setSubject(d);
      setError(null);
      if (selectedVersion === null && d.versions.length > 0) {
        setSelectedVersion(d.versions[d.versions.length - 1].version_no);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [subjectId, selectedVersion]);

  useEffect(() => {
    void fetchSubject();
  }, [fetchSubject]);

  useEffect(() => {
    if (!subject || selectedVersion === null) return;
    let cancelled = false;
    setGraphLoading(true);
    async function load() {
      try {
        const r = await fetch(
          `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(
            subjectId,
          )}/versions/${selectedVersion}/graph?depth=1`,
          { cache: "no-store" },
        );
        if (!r.ok) throw new Error(`graph ${r.status}`);
        const d: GraphPayload = await r.json();
        if (cancelled) return;
        setGraph(d);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [subject, selectedVersion, subjectId]);

  // Poll while a run is in flight so the timeline updates without manual refresh.
  useEffect(() => {
    if (!subject) return;
    const pending = subject.versions.find(
      (v) => v.status === "running" || v.status === "pending",
    );
    if (!pending) return;
    const handle = setInterval(() => {
      void fetchSubject();
    }, 4000);
    return () => clearInterval(handle);
  }, [subject, fetchSubject]);

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    try {
      const r = await fetch(
        `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ triggered_by: "manual" }),
        },
      );
      if (r.status === 409) {
        setRunError(isZh ? "已有分析在跑,请稍后" : "Another run is in flight; try later");
      } else if (r.status === 503) {
        const d = await r.json().catch(() => ({ detail: "503" }));
        setRunError(`${d.detail || "503"}`);
      } else if (!r.ok) {
        setRunError(`HTTP ${r.status}`);
      } else {
        await fetchSubject();
      }
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const activeVersion =
    subject && selectedVersion !== null
      ? subject.versions.find((v) => v.version_no === selectedVersion) ?? null
      : null;

  return (
    <PortalShell
      active="industry"
      locale={locale}
      onLocaleChange={changeLocale}
      title={subject?.display_name ?? (isZh ? "加载中…" : "Loading…")}
      subtitle={
        subject
          ? isZh
            ? `${subject.type === "company" ? "公司" : "主题"} · ${subject.target_entity_id}`
            : `${subject.type} · ${subject.target_entity_id}`
          : undefined
      }
      actions={
        <Link href="/industry-graph" className="live-pill">
          {isZh ? "← 返回列表" : "← back to list"}
        </Link>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="ig-detail-workspace">
        {/* LEFT — vertical version timeline */}
        <aside className="ig-detail-timeline">
          <div className="live-themes-header">
            <span className="label">{isZh ? "版本历史" : "History"}</span>
            <span className="muted">
              {subject ? `v${subject.versions.length}` : ""}
            </span>
          </div>

          {loading ? (
            <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>
          ) : !subject ? (
            <p className="muted live-empty">{isZh ? "未找到 subject" : "subject not found"}</p>
          ) : (
            <>
              <ul className="ig-timeline">
                {[...subject.versions].reverse().map((v) => {
                  const isActive = v.version_no === selectedVersion;
                  return (
                    <li
                      key={v.id}
                      className={`ig-timeline-row ${isActive ? "active" : ""} status-${v.status}`}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedVersion(v.version_no)}
                        className="ig-timeline-button"
                      >
                        <span className="ig-timeline-dot" />
                        <span className="ig-timeline-meta">
                          <span className="ig-timeline-ver">v{v.version_no}</span>
                          <span className="ig-timeline-when">
                            {shortDate(v.ended_at ?? v.started_at)}
                          </span>
                        </span>
                        <span className="ig-timeline-rationale">
                          {v.rationale || v.task_prompt?.slice(0, 60) || v.triggered_by}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="ig-timeline-actions">
                <button
                  type="button"
                  onClick={handleRun}
                  disabled={running}
                  className="ig-run-btn"
                >
                  {running ? (isZh ? "提交中…" : "Starting…") : isZh ? "+ 新分析" : "+ Run new"}
                </button>
                {runError ? <p className="muted error-copy">{runError}</p> : null}
              </div>
            </>
          )}
        </aside>

        {/* MIDDLE — graph + version details */}
        <section className="ig-detail-main">
          <div className="ig-graph-area">
            {graphLoading ? (
              <p className="muted live-empty">{isZh ? "渲染中…" : "Rendering…"}</p>
            ) : !graph || graph.nodes.length === 0 ? (
              <p className="muted live-empty">
                {isZh
                  ? "这个版本对应的锚点在图中暂未找到。"
                  : "Anchor not present at this version's snapshot."}
              </p>
            ) : (
              <SubjectGraph
                payload={graph}
                anchorId={subject?.target_entity_id ?? ""}
                showOrphans={false}
                showLabels={true}
              />
            )}
          </div>

          <div className="ig-version-card">
            {activeVersion ? (
              <>
                <div className="ig-version-header">
                  <span className="ig-version-eyebrow">
                    {isZh ? `v${activeVersion.version_no} · 详情` : `v${activeVersion.version_no} · details`}
                  </span>
                  <span className={`ig-version-status status-${activeVersion.status}`}>
                    {activeVersion.status}
                  </span>
                </div>
                <dl className="ig-version-dl">
                  <dt>{isZh ? "触发方" : "trigger"}</dt>
                  <dd>{activeVersion.triggered_by}</dd>
                  <dt>{isZh ? "Agent" : "agent"}</dt>
                  <dd>
                    {activeVersion.run_id}
                    {activeVersion.task_prompt
                      ? ` · ${activeVersion.task_prompt.length}ch prompt`
                      : ""}
                  </dd>
                  <dt>{isZh ? "Snapshot" : "snapshot"}</dt>
                  <dd>
                    v{activeVersion.snapshot_from} → v{activeVersion.snapshot_to}
                  </dd>
                  <dt>{isZh ? "时间" : "ended"}</dt>
                  <dd>
                    {formatRelative(
                      activeVersion.ended_at ?? activeVersion.started_at,
                      locale,
                    )}
                  </dd>
                  {activeVersion.change_summary ? (
                    <>
                      <dt>{isZh ? "变更" : "changes"}</dt>
                      <dd>
                        +{activeVersion.change_summary.entities_added} ent · +
                        {activeVersion.change_summary.relations_added} rel
                      </dd>
                    </>
                  ) : null}
                  {activeVersion.error ? (
                    <>
                      <dt>{isZh ? "错误" : "error"}</dt>
                      <dd className="error-copy">{activeVersion.error}</dd>
                    </>
                  ) : null}
                </dl>
                {activeVersion.change_summary?.highlights?.length ? (
                  <ul className="ig-version-highlights">
                    {activeVersion.change_summary.highlights.slice(0, 6).map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    {isZh ? "本版本没有变更摘要。" : "No changes recorded for this version."}
                  </p>
                )}
              </>
            ) : (
              <p className="muted">{isZh ? "选一个版本查看详情" : "Pick a version"}</p>
            )}
          </div>
        </section>
      </div>
    </PortalShell>
  );
}
