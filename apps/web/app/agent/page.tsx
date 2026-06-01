"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActiveWorkPanel } from "../../components/portal/ActiveWorkPanel";
import { AgentHeartrate } from "../../components/portal/AgentHeartrate";
import { AgentIdentity } from "../../components/portal/AgentIdentity";
import { CapabilityConfig } from "../../components/portal/CapabilityConfig";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";

type AgentSummary = {
  identity: {
    name: string;
    chinese_name: string;
    tagline_en: string;
    tagline_zh: string;
    version: string;
  };
  status: {
    status: "idle" | "running" | "awaiting_checkpoint";
    active_run_id: string | null;
    awaiting_run_id: string | null;
    last_activity_ts: number | null;
    since_first_activity_ts: number | null;
  };
  heartrate: {
    total_runs: number;
    active_runs: number;
    awaiting_checkpoints: number;
    completed_runs: number;
    failed_runs: number;
    total_hypotheses: number;
    active_hypotheses: number;
    falsified_hypotheses: number;
    total_dossiers: number;
    total_patches_proposed: number;
    total_critic_verdicts: number;
    total_critic_rejects: number;
    total_injections: number;
    total_spirals: number;
  };
  capabilities: {
    triggers: Array<{
      key: string;
      name_en: string;
      name_zh: string;
      default: unknown;
      description_en: string;
      description_zh: string;
      options: unknown[];
    }>;
  };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function AgentPage() {
  const [summary, setSummary] = useState<AgentSummary | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";

  function changeLocale(nextLocale: Locale) {
    setLocale(nextLocale);
    window.localStorage.setItem("shinkai.locale", nextLocale);
  }

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/agent/summary`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`${response.status}`);
        const data: AgentSummary = await response.json();
        if (!cancelled) {
          setSummary(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    const id = window.setInterval(load, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <PortalShell
      active="agent"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "Agent 概况" : "Agent Overview"}
      subtitle={
        isZh
          ? "shinkai 现在是谁、心率几何、装备什么。"
          : "Who shinkai is right now — identity, heartrate, equipment."
      }
      actions={
        <>
          <Link className="button secondary" href="/results">
            {isZh ? "查看过往产出" : "Past Results"}
          </Link>
          <Link className="button" href="/runs">
            {isZh ? "运行历史" : "Run History"}
          </Link>
        </>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}
      {summary ? (
        <div className="agent-overview">
          <AgentIdentity
            name={summary.identity.name}
            chineseName={summary.identity.chinese_name}
            taglineEn={summary.identity.tagline_en}
            taglineZh={summary.identity.tagline_zh}
            version={summary.identity.version}
            status={summary.status.status}
            lastActivityTs={summary.status.last_activity_ts}
            locale={locale}
          />
          <AgentHeartrate
            heartrate={summary.heartrate}
            sinceFirstActivityTs={summary.status.since_first_activity_ts}
            locale={locale}
          />
          <div className="agent-overview-row">
            <ActiveWorkPanel locale={locale} />
            <CapabilityConfig triggers={summary.capabilities.triggers} locale={locale} />
          </div>
        </div>
      ) : (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      )}
    </PortalShell>
  );
}
