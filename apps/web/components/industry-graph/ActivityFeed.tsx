"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export type ActivityRow = {
  event_id: string;
  run_id: string;
  run_anchor: string;
  type: "company_dossier_created" | "company_deep_analysis_completed" | "judgment_created";
  ts: number;
  summary: string;
  subject_id: string;
  data: Record<string, unknown>;
};

type ActivityResponse = {
  rows: ActivityRow[];
  count: number;
};

type SubjectLookupRow = {
  id: string;
  display_name: string;
  type: "company" | "theme";
};

type Props = {
  // When set, fetch /subjects/{id}/activity instead of /activity.
  subjectId?: string;
  // Pre-resolved id → display_name for subject chips. The list page already
  // has the full list, so we lift the lookup up to avoid a second fetch.
  subjectLookup?: Map<string, SubjectLookupRow>;
  limit?: number;
  locale: Locale;
};

function eventBadge(t: ActivityRow["type"], locale: Locale): string {
  if (locale === "zh") {
    if (t === "company_dossier_created") return "档案";
    if (t === "company_deep_analysis_completed") return "深析";
    if (t === "judgment_created") return "判断";
    return t;
  }
  if (t === "company_dossier_created") return "dossier";
  if (t === "company_deep_analysis_completed") return "deep";
  if (t === "judgment_created") return "judgment";
  return t;
}

function formatTime(ts: number, locale: Locale): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  const delta = (Date.now() - d.getTime()) / 1000;
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
  return d.toISOString().slice(0, 10);
}

export function ActivityFeed({
  subjectId,
  subjectLookup,
  limit = 60,
  locale,
}: Props) {
  const isZh = locale === "zh";
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    async function load() {
      try {
        const url = subjectId
          ? `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}/activity?limit=${limit}`
          : `${API_URL}/api/v1/industry_graph/activity?limit=${limit}`;
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) throw new Error(`activity ${r.status}`);
        const d: ActivityResponse = await r.json();
        if (cancelled) return;
        setRows(d.rows);
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
  }, [subjectId, limit]);

  if (loading) {
    return <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>;
  }
  if (error) {
    return <p className="muted error-copy">{error}</p>;
  }
  if (rows.length === 0) {
    return (
      <p className="muted live-empty">
        {subjectId
          ? isZh
            ? "尚无历史 Run 涉及此 Subject。"
            : "No historical Run events have touched this Subject yet."
          : isZh
            ? "尚无分析活动。跑一次 Mode B 之后这里会有内容。"
            : "No analytical activity yet. Mode B runs populate this feed."}
      </p>
    );
  }

  return (
    <ul className="ig-activity-list">
      {rows.map((r) => {
        const subj = subjectLookup?.get(r.subject_id);
        return (
          <li key={`${r.event_id}-${r.subject_id}`} className="ig-activity">
            <Link
              href={`/industry-graph/${encodeURIComponent(r.subject_id)}?event=${r.event_id}`}
              className="ig-activity-link"
            >
              <div className="ig-activity-row1">
                <span className={`ig-activity-badge type-${r.type}`}>
                  {eventBadge(r.type, locale)}
                </span>
                <span className="ig-activity-time">{formatTime(r.ts, locale)}</span>
                {subj ? (
                  <span className="ig-activity-subject">
                    {subj.display_name}
                    <span className={`ig-activity-type-chip type-${subj.type}`}>
                      {subj.type === "company"
                        ? isZh
                          ? "公司"
                          : "co"
                        : isZh
                          ? "主题"
                          : "th"}
                    </span>
                  </span>
                ) : (
                  <span className="ig-activity-subject">{r.subject_id}</span>
                )}
              </div>
              {r.summary ? <p className="ig-activity-summary">{r.summary}</p> : null}
              {r.run_anchor ? (
                <p className="ig-activity-anchor">
                  {isZh ? "来自 Run · " : "from Run · "}
                  {r.run_anchor}
                </p>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
