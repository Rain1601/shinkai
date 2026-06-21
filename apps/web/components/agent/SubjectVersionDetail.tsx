"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PortalShell } from "../portal/PortalShell";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type RunDetail = {
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
  scope_node_ids: string[];
  task_prompt: string;
  rationale: string;
  change_summary: {
    entities_added: number;
    entities_updated: number;
    entities_deprecated: number;
    relations_added: number;
    relations_updated: number;
    relations_deprecated: number;
    highlights: string[];
  } | null;
  error?: string | null;
};

function formatAbsolute(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function durationSec(a: string, b: string | null): string {
  if (!b) return "—";
  const t0 = new Date(a).getTime();
  const t1 = new Date(b).getTime();
  if (Number.isNaN(t0) || Number.isNaN(t1)) return "—";
  const sec = Math.round((t1 - t0) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

type Props = {
  svId: string;
};

export function SubjectVersionDetail({ svId }: Props) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
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
    setLoading(true);
    async function load() {
      try {
        const r = await fetch(
          `${API_URL}/api/v1/industry_graph/runs/${encodeURIComponent(svId)}`,
          { cache: "no-store" },
        );
        if (!r.ok) throw new Error(`run ${r.status}`);
        const d: RunDetail = await r.json();
        if (cancelled) return;
        setDetail(d);
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
  }, [svId]);

  return (
    <PortalShell
      active="history"
      locale={locale}
      onLocaleChange={changeLocale}
      title={detail ? `v${detail.version_no} · ${detail.subject_display_name}` : isZh ? "加载中…" : "Loading…"}
      subtitle={
        detail
          ? isZh
            ? `${detail.subject_type === "company" ? "公司" : "主题"} · ${detail.target_entity_id} · SubjectVersion`
            : `${detail.subject_type} · ${detail.target_entity_id} · SubjectVersion`
          : undefined
      }
      actions={
        <>
          <Link href="/runs" className="live-pill">
            {isZh ? "← 运行日志" : "← Run log"}
          </Link>
          {detail ? (
            <Link
              href={`/agent/${encodeURIComponent(detail.subject_id)}`}
              className="ig-run-btn"
              style={{ width: "auto", padding: "8px 14px", marginLeft: 8 }}
            >
              {isZh ? "打开 Subject →" : "Open Subject →"}
            </Link>
          ) : null}
        </>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      {loading || !detail ? (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      ) : (
        <div className="sv-detail">
          <section className="sv-detail-meta">
            <span className={`runs-row-status status-${detail.status}`} style={{ alignSelf: "flex-start" }}>
              {detail.status}
            </span>
            <dl>
              <dt>{isZh ? "触发方" : "trigger"}</dt>
              <dd>{detail.triggered_by}</dd>
              <dt>{isZh ? "Agent" : "agent"}</dt>
              <dd>{detail.run_id}</dd>
              <dt>{isZh ? "Snapshot" : "snapshot"}</dt>
              <dd>
                v{detail.snapshot_from} → v{detail.snapshot_to}
              </dd>
              <dt>{isZh ? "开始" : "started"}</dt>
              <dd>{formatAbsolute(detail.started_at)}</dd>
              <dt>{isZh ? "结束" : "ended"}</dt>
              <dd>{formatAbsolute(detail.ended_at)}</dd>
              <dt>{isZh ? "耗时" : "duration"}</dt>
              <dd>{durationSec(detail.started_at, detail.ended_at)}</dd>
              <dt>{isZh ? "Scope · 节点" : "scope · nodes"}</dt>
              <dd>{detail.scope_node_ids.length}</dd>
            </dl>
          </section>

          {detail.error ? (
            <section className="sv-detail-error">
              <header>
                <h2>{isZh ? "错误" : "Error"}</h2>
              </header>
              <pre>{detail.error}</pre>
            </section>
          ) : null}

          {detail.task_prompt ? (
            <section className="sv-detail-block">
              <header>
                <h2>{isZh ? "任务 · Task" : "Task"}</h2>
              </header>
              <p className="sv-detail-task">{detail.task_prompt}</p>
            </section>
          ) : null}

          {detail.rationale ? (
            <section className="sv-detail-block">
              <header>
                <h2>{isZh ? "结论 · Rationale" : "Rationale"}</h2>
              </header>
              <p className="sv-detail-rationale">{detail.rationale}</p>
            </section>
          ) : null}

          {detail.change_summary ? (
            <section className="sv-detail-block">
              <header>
                <h2>{isZh ? "变更摘要 · Changes" : "Change summary"}</h2>
              </header>
              <table className="sv-detail-changes">
                <tbody>
                  <tr>
                    <th>{isZh ? "实体新增" : "entities added"}</th>
                    <td>{detail.change_summary.entities_added}</td>
                    <th>{isZh ? "关系新增" : "relations added"}</th>
                    <td>{detail.change_summary.relations_added}</td>
                  </tr>
                  <tr>
                    <th>{isZh ? "实体更新" : "entities updated"}</th>
                    <td>{detail.change_summary.entities_updated}</td>
                    <th>{isZh ? "关系更新" : "relations updated"}</th>
                    <td>{detail.change_summary.relations_updated}</td>
                  </tr>
                  <tr>
                    <th>{isZh ? "实体废弃" : "entities deprecated"}</th>
                    <td>{detail.change_summary.entities_deprecated}</td>
                    <th>{isZh ? "关系废弃" : "relations deprecated"}</th>
                    <td>{detail.change_summary.relations_deprecated}</td>
                  </tr>
                </tbody>
              </table>
              {detail.change_summary.highlights.length > 0 ? (
                <ul className="sv-detail-highlights">
                  {detail.change_summary.highlights.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : detail.triggered_by === "migration" ? (
            <p className="muted">
              {isZh
                ? "这是 migration baseline,没有变更摘要。"
                : "Migration baseline; no change summary."}
            </p>
          ) : null}

          {detail.scope_node_ids.length > 0 ? (
            <section className="sv-detail-block">
              <header>
                <h2>{isZh ? "范围 · Scope" : "Scope"}</h2>
              </header>
              <ul className="sv-detail-scope">
                {detail.scope_node_ids.slice(0, 50).map((id) => (
                  <li key={id}>{id}</li>
                ))}
                {detail.scope_node_ids.length > 50 ? (
                  <li className="muted">
                    +{detail.scope_node_ids.length - 50}{" "}
                    {isZh ? "条未显示" : "more"}
                  </li>
                ) : null}
              </ul>
            </section>
          ) : null}
        </div>
      )}
    </PortalShell>
  );
}
