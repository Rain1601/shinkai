"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";
import { localizeStatus, localizeText } from "../../lib/i18n";

type RunEvent = {
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type Run = {
  id: string;
  anchor: string;
  status: string;
  lifecycle_stage: string;
  events: RunEvent[];
};

type ActiveWorkPanelProps = {
  locale: Locale;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";
const TERMINAL = new Set(["completed", "failed", "aborted"]);

function latestJudgment(events: RunEvent[]): { layer: string; confidence: number | null } | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event.type === "judgment_created") {
      return {
        layer: String(event.data?.layer ?? ""),
        confidence:
          typeof event.data?.confidence === "number" ? event.data.confidence : null,
      };
    }
  }
  return null;
}

function elapsed(events: RunEvent[], isZh: boolean): string {
  const timestamps = events
    .map((event) => event.ts)
    .filter((ts): ts is number => typeof ts === "number");
  if (timestamps.length === 0) return isZh ? "刚开始" : "starting";
  const start = Math.min(...timestamps);
  const now = Date.now() / 1000;
  const delta = Math.floor(now - start);
  if (delta < 60) return isZh ? `${delta} 秒` : `${delta}s`;
  if (delta < 3600) return isZh ? `${Math.floor(delta / 60)} 分钟` : `${Math.floor(delta / 60)}m`;
  return isZh ? `${Math.floor(delta / 3600)} 小时` : `${Math.floor(delta / 3600)}h`;
}

export function ActiveWorkPanel({ locale }: ActiveWorkPanelProps) {
  const isZh = locale === "zh";
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/runs`, { cache: "no-store" });
        if (!response.ok) throw new Error(`${response.status}`);
        const data: Run[] = await response.json();
        if (!cancelled) {
          setRuns(data.filter((run) => !TERMINAL.has(run.status)));
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    const id = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <section className="surface active-work-panel">
      <div className="panel-heading">
        <h2>{isZh ? "当下工作" : "Active Work"}</h2>
        <span className="label">{runs.length}</span>
      </div>
      {error ? <p className="muted error-copy">{error}</p> : null}
      {runs.length === 0 ? (
        <p className="muted active-work-idle">
          {isZh
            ? "Agent 空闲。到运行历史启动一次扫描,或在主题里挑一个回访。"
            : "Agent is idle. Start a new scan from History."}
        </p>
      ) : (
        <div className="active-work-list">
          {runs.map((run) => {
            const judgment = latestJudgment(run.events);
            return (
              <Link
                className="active-work-row"
                href={`/runs/${run.id}?tab=cockpit`}
                key={run.id}
              >
                <div className="active-work-row-header">
                  <strong>{localizeText(run.anchor, locale)}</strong>
                  <span className={`pill pill-state-${run.status === "awaiting_checkpoint" ? "active" : "active"}`}>
                    {localizeStatus(run.status, locale)}
                  </span>
                </div>
                <div className="active-work-row-body">
                  {judgment ? (
                    <span>
                      {isZh ? "当前判断" : "Judgment"}:{" "}
                      <em>{judgment.layer || (isZh ? "未命名层" : "unnamed")}</em>
                      {judgment.confidence !== null
                        ? ` · ${(judgment.confidence * 100).toFixed(0)}%`
                        : ""}
                    </span>
                  ) : (
                    <span className="muted">{isZh ? "尚未形成判断" : "no judgment yet"}</span>
                  )}
                </div>
                <div className="active-work-row-meta">
                  <span>
                    {isZh ? "已运行" : "Elapsed"} {elapsed(run.events, isZh)}
                  </span>
                  <code>#{run.id.slice(0, 8)}</code>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
