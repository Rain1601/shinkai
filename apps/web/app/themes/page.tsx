"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";
import { localizeText } from "../../lib/i18n";

type ThemeSummary = {
  theme_id: string;
  title: string;
  run_count: number;
  active_hypothesis_count: number;
  falsified_hypothesis_count: number;
  last_activity_ts: number;
  latest_run_id: string | null;
  running_count: number;
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

export default function ThemesPage() {
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [locale, setLocale] = useState<Locale>("zh");
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/themes`, { cache: "no-store" });
        if (!response.ok) throw new Error(`${response.status}`);
        const data: ThemeSummary[] = await response.json();
        if (!cancelled) setThemes(data);
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
  }, []);

  return (
    <PortalShell
      active="themes"
      locale={locale}
      title={isZh ? "主题" : "Themes"}
      subtitle={
        isZh
          ? "跨 run 的主题聚合视图。每个主题下,agent 持续追踪同组假设的状态变化。"
          : "Cross-run aggregation. Each theme tracks how a single set of hypotheses evolves."
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}
      <section className="theme-grid">
        {themes.length === 0 && !error ? (
          <p className="muted">
            {isZh ? "暂无主题,先到运行页启动一次扫描。" : "No themes yet."}
          </p>
        ) : null}
        {themes.map((theme) => (
          <article className="surface theme-tile" key={theme.theme_id}>
            <header>
              <h2>{localizeText(theme.title, locale)}</h2>
              <span className="label">
                {isZh
                  ? `${theme.run_count} 次 · ${theme.running_count} 运行中`
                  : `${theme.run_count} runs · ${theme.running_count} active`}
              </span>
            </header>
            <p className="muted">
              {isZh
                ? `活跃假设 ${theme.active_hypothesis_count} · 已证伪 ${theme.falsified_hypothesis_count}`
                : `${theme.active_hypothesis_count} active · ${theme.falsified_hypothesis_count} falsified`}
              {" · "}
              {formatTime(theme.last_activity_ts, locale)}
            </p>
            <div className="theme-tile-actions">
              <Link className="button" href={`/themes/${theme.theme_id}`}>
                {isZh ? "查看主题" : "Open theme"}
              </Link>
              {theme.latest_run_id ? (
                <Link
                  className="button secondary"
                  href={`/runs/${theme.latest_run_id}`}
                >
                  {isZh ? "最新一次 run" : "Latest run"}
                </Link>
              ) : null}
            </div>
          </article>
        ))}
      </section>
    </PortalShell>
  );
}
