"use client";

import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";

type RunEvent = {
  type?: string;
  data?: Record<string, unknown>;
  ts?: number;
};

type RunSummary = {
  id: string;
  anchor: string;
  status: string;
  events?: RunEvent[];
};

type CheckpointBannerProps = {
  locale?: Locale;
  pollIntervalMs?: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

function latestCheckpointPrompt(events: RunEvent[] | undefined): {
  reason: string;
  prompt: string;
} | null {
  if (!events) return null;
  const cps = events.filter((event) => event.type === "checkpoint_raised");
  if (cps.length === 0) return null;
  const last = cps[cps.length - 1];
  return {
    reason: String(last.data?.reason ?? ""),
    prompt: String(last.data?.prompt ?? ""),
  };
}

export function CheckpointBanner({
  locale = "zh",
  pollIntervalMs = 5000,
}: CheckpointBannerProps) {
  const isZh = locale === "zh";
  const [awaitingRuns, setAwaitingRuns] = useState<RunSummary[]>([]);
  const [submitting, setSubmitting] = useState<string | null>(null);

  async function poll() {
    try {
      const response = await fetch(`${API_URL}/api/v1/runs`, { cache: "no-store" });
      if (!response.ok) return;
      const runs: RunSummary[] = await response.json();
      setAwaitingRuns(runs.filter((run) => run.status === "awaiting_checkpoint"));
    } catch {
      // network errors silent
    }
  }

  useEffect(() => {
    poll();
    const id = window.setInterval(poll, pollIntervalMs);
    return () => window.clearInterval(id);
  }, [pollIntervalMs]);

  async function resolve(runId: string, decision: "approve" | "reject") {
    if (decision === "reject") {
      const ok = window.confirm(
        isZh ? "确认拒绝并终止此次运行?" : "Reject and abort this run?"
      );
      if (!ok) return;
    }
    setSubmitting(runId);
    try {
      await fetch(`${API_URL}/api/v1/runs/${runId}/checkpoint`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, note: "" }),
      });
      await poll();
    } finally {
      setSubmitting(null);
    }
  }

  if (awaitingRuns.length === 0) return null;
  const first = awaitingRuns[0];
  const promptInfo = latestCheckpointPrompt(first.events);
  const extraCount = awaitingRuns.length - 1;

  return (
    <div className="checkpoint-banner" role="status">
      <div className="checkpoint-banner-body">
        <strong>{isZh ? "等待审阅" : "Awaiting review"}</strong>
        <span className="checkpoint-banner-anchor">
          {first.anchor} <code>#{first.id.slice(0, 8)}</code>
        </span>
        {promptInfo?.prompt ? (
          <span className="checkpoint-banner-prompt">{promptInfo.prompt}</span>
        ) : null}
        {extraCount > 0 ? (
          <span className="checkpoint-banner-extra">
            {isZh ? `另外 ${extraCount} 个等待中` : `+${extraCount} more`}
          </span>
        ) : null}
      </div>
      <div className="checkpoint-banner-actions">
        <button
          className="button"
          type="button"
          disabled={submitting === first.id}
          onClick={() => resolve(first.id, "approve")}
        >
          {isZh ? "批准并继续" : "Approve"}
        </button>
        <button
          className="button danger"
          type="button"
          disabled={submitting === first.id}
          onClick={() => resolve(first.id, "reject")}
        >
          {isZh ? "拒绝并终止" : "Reject"}
        </button>
      </div>
    </div>
  );
}
