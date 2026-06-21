"use client";

import { useEffect, useState } from "react";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type SubjectListRow = {
  id: string;
  latest_version: { status: string } | null;
};

type Props = {
  locale: Locale;
};

/**
 * Thin agent-identity row mounted above the page header on every workspace
 * (`/agent`, `/agent/[subjectId]`) and run-log route (`/runs`, `/runs/sv:*`).
 *
 * The status dot polls `/api/v1/industry_graph/subjects` every 30s and is
 * "running" iff any Subject's latest version is in flight (running or
 * pending). Falls back to "空闲 / Idle" when the agent has nothing on.
 *
 * Kept minimal on purpose — the surrounding page header carries the actual
 * title/subtitle, this strip just brands the workspace as the agent's.
 */
export function AgentIdentityStrip({ locale }: Props) {
  const isZh = locale === "zh";
  const [runningCount, setRunningCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch(`${API_URL}/api/v1/industry_graph/subjects`, {
          cache: "no-store",
        });
        if (!r.ok) return;
        const d: { subjects: SubjectListRow[] } = await r.json();
        if (cancelled) return;
        const count = d.subjects.filter(
          (s) =>
            s.latest_version?.status === "running" ||
            s.latest_version?.status === "pending",
        ).length;
        setRunningCount(count);
      } catch {}
    }
    void load();
    const handle = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, []);

  const status = runningCount && runningCount > 0 ? "running" : "idle";

  return (
    <div className="agent-identity-strip" data-status={status}>
      <span className="agent-identity-brand">
        <span className="agent-identity-display">shinkai · 深海</span>
        <span className="agent-identity-sublabel">
          {isZh ? "持续研究 Agent" : "Continuous research agent"}
        </span>
      </span>
      <span className="agent-identity-status">
        <span className={`agent-identity-dot ${status}`} aria-hidden />
        <span className="agent-identity-status-text">
          {status === "running"
            ? isZh
              ? `${runningCount} 在跑`
              : `${runningCount} active`
            : isZh
              ? "空闲"
              : "Idle"}
        </span>
      </span>
    </div>
  );
}
