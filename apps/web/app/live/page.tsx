"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LiveCockpit } from "../../components/portal/LiveCockpit";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";

type LiveEvent = {
  event_id: string;
  type: string;
  ts: number | null;
  summary: string;
};

type LiveRun = {
  run_id: string;
  anchor: string;
  status: string;
  lifecycle_stage: string;
  elapsed_seconds: number;
  judgment: {
    hypothesis_id: string | null;
    layer: string;
    judgment: string;
    confidence: number | null;
  } | null;
  recent_events: LiveEvent[];
};

type LiveResponse = {
  idle: boolean;
  active: LiveRun | null;
  last_completed: LiveRun | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function LivePage() {
  const [data, setData] = useState<LiveResponse | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const isZh = locale === "zh";

  function changeLocale(next: Locale) {
    setLocale(next);
    window.localStorage.setItem("shinkai.locale", next);
  }

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/agent/live`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const next: LiveResponse = await response.json();
        if (!cancelled) setData(next);
      } catch {
        // silent
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
    <PortalShell
      active="live"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "实时" : "Live"}
      subtitle={
        isZh
          ? "Agent 现在在干什么 — 最近的活跃 run、当前判断与最近事件。"
          : "What the agent is doing right now — current run, judgment, latest events."
      }
      actions={
        <Link className="button secondary" href="/runs">
          {isZh ? "查看历史" : "History"}
        </Link>
      }
    >
      {!data ? (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      ) : data.active ? (
        <LiveCockpit run={data.active} locale={locale} />
      ) : data.last_completed ? (
        <>
          <p className="live-idle-note">
            {isZh
              ? "Agent 当前空闲 — 下方是最近一次完成的运行,作上下文。"
              : "Agent is idle — the most recently completed run is shown below as context."}
          </p>
          <LiveCockpit
            run={data.last_completed}
            locale={locale}
            label={isZh ? "最近完成" : "Last completed"}
          />
        </>
      ) : (
        <p className="live-idle-note">
          {isZh ? "Agent 当前空闲,且尚无任何运行历史。" : "Agent is idle and there are no past runs yet."}
        </p>
      )}
    </PortalShell>
  );
}
