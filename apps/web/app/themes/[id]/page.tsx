"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PortalShell } from "../../../components/portal/PortalShell";
import type { Locale } from "../../../lib/i18n";
import {
  formatNumber,
  localizeStatus,
  localizeText,
} from "../../../lib/i18n";
import { useLastSeen } from "../../../lib/useLastSeen";

type Hypothesis = {
  hypothesis_id: string;
  run_id: string;
  layer: string;
  claim: string;
  confidence: number;
  state: "active" | "falsified" | "superseded";
  falsification_condition: string;
};

type ThemeRunSummary = {
  run_id: string;
  status: string;
  lifecycle_stage: string;
  anchor: string;
  last_activity_ts: number;
};

type ThemeDetail = {
  theme_id: string;
  title: string;
  runs: ThemeRunSummary[];
  active_hypotheses: Hypothesis[];
  falsified_hypotheses: Hypothesis[];
  procedural_memory: unknown[];
  next_reschedule: string | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

function formatTime(ts: number, locale: Locale): string {
  if (!ts) return locale === "zh" ? "暂无" : "n/a";
  return new Date(ts * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ThemeDetailPage() {
  const params = useParams<{ id: string }>();
  const themeId = params.id;
  const [locale, setLocale] = useState<Locale>("zh");
  const [theme, setTheme] = useState<ThemeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";
  useLastSeen(themeId ? `theme:${themeId}` : null);

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
    if (!themeId) return;
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/themes/${themeId}`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`${response.status}`);
        const data: ThemeDetail = await response.json();
        if (!cancelled) setTheme(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    const id = window.setInterval(load, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [themeId]);

  return (
    <PortalShell
      active="themes"
      locale={locale}
      title={theme ? localizeText(theme.title, locale) : isZh ? "主题" : "Theme"}
      subtitle={
        theme
          ? `${theme.runs.length} ${isZh ? "次 run" : "runs"} · ${theme.active_hypotheses.length} ${isZh ? "活跃假设" : "active hypotheses"}`
          : undefined
      }
      actions={
        <Link className="button secondary" href="/themes">
          {isZh ? "← 主题列表" : "← All themes"}
        </Link>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}
      {!theme ? (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      ) : (
        <div className="theme-detail">
          <section className="surface">
            <div className="panel-heading">
              <h2>{isZh ? "活跃假设" : "Active Hypotheses"}</h2>
              <span className="label">{theme.active_hypotheses.length}</span>
            </div>
            {theme.active_hypotheses.length === 0 ? (
              <p className="muted">
                {isZh ? "暂无活跃假设。" : "No active hypotheses yet."}
              </p>
            ) : (
              <div className="theme-hypothesis-list">
                {theme.active_hypotheses.map((hyp) => (
                  <article
                    className="theme-hypothesis-card"
                    key={hyp.hypothesis_id}
                  >
                    <header>
                      <strong>{hyp.layer}</strong>
                      <span className="hypothesis-confidence-value">
                        {formatNumber(hyp.confidence)}
                      </span>
                    </header>
                    <p>{hyp.claim}</p>
                    {hyp.falsification_condition ? (
                      <p className="muted small">
                        {isZh ? "证伪条件" : "Falsification"}:{" "}
                        {hyp.falsification_condition}
                      </p>
                    ) : null}
                    <Link
                      className="link-button"
                      href={`/runs/${hyp.run_id}?tab=framework`}
                    >
                      {isZh ? "查看推理树" : "Inspect reasoning tree"} →
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>

          {theme.falsified_hypotheses.length > 0 ? (
            <section className="surface">
              <div className="panel-heading">
                <h2>{isZh ? "已证伪假设" : "Falsified Hypotheses"}</h2>
                <span className="label">{theme.falsified_hypotheses.length}</span>
              </div>
              <ul className="theme-falsified-list">
                {theme.falsified_hypotheses.map((hyp) => (
                  <li key={hyp.hypothesis_id}>
                    <strong>{hyp.layer}</strong>{" "}
                    <span className="muted">
                      {hyp.falsification_condition || hyp.claim}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="surface">
            <div className="panel-heading">
              <h2>{isZh ? "历史运行" : "Run history"}</h2>
              <span className="label">{theme.runs.length}</span>
            </div>
            <div className="theme-tile-runs">
              {theme.runs.map((run, index) => (
                <Link
                  className="theme-run-chip"
                  href={`/runs/${run.run_id}`}
                  key={run.run_id}
                >
                  <span>
                    {isZh
                      ? `第 ${theme.runs.length - index} 次`
                      : `Run ${theme.runs.length - index}`}
                  </span>
                  <strong>{localizeStatus(run.status, locale)}</strong>
                  <small>{formatTime(run.last_activity_ts, locale)}</small>
                </Link>
              ))}
            </div>
          </section>

          <section className="surface">
            <div className="panel-heading">
              <h2>{isZh ? "可迭代占位" : "Iteration"}</h2>
              <span className="label">{isZh ? "未建" : "pending"}</span>
            </div>
            <p className="muted">
              {isZh
                ? "Procedural memory(跨 run 学到的策略)与「下次自主重跑」调度尚未实现 — 留给 P4 / P6。"
                : "Procedural memory and auto-reschedule are not yet implemented; see P4 / P6."}
            </p>
          </section>
        </div>
      )}
    </PortalShell>
  );
}
