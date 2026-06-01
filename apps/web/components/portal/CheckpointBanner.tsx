"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";

type RunSummary = {
  id: string;
  anchor: string;
  status: string;
};

type CheckpointBannerProps = {
  locale?: Locale;
  pollIntervalMs?: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export function CheckpointBanner({
  locale = "zh",
  pollIntervalMs = 5000,
}: CheckpointBannerProps) {
  const isZh = locale === "zh";
  const [awaitingRuns, setAwaitingRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const response = await fetch(`${API_URL}/api/v1/runs`, { cache: "no-store" });
        if (!response.ok) return;
        const runs: RunSummary[] = await response.json();
        if (cancelled) return;
        setAwaitingRuns(runs.filter((run) => run.status === "awaiting_checkpoint"));
      } catch {
        // Network errors are silent — banner just stays empty.
      }
    }
    poll();
    const id = window.setInterval(poll, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollIntervalMs]);

  if (awaitingRuns.length === 0) return null;
  const first = awaitingRuns[0];
  const extraCount = awaitingRuns.length - 1;

  return (
    <div className="checkpoint-banner" role="status">
      <span>
        <strong>
          {isZh ? "等待审阅" : "Awaiting review"}
        </strong>
        {" — "}
        {isZh
          ? `${first.anchor} (#${first.id.slice(0, 8)}) 已暂停`
          : `${first.anchor} (#${first.id.slice(0, 8)}) is paused`}
        {extraCount > 0
          ? isZh
            ? ` 以及另外 ${extraCount} 个`
            : ` and ${extraCount} more`
          : ""}
      </span>
      <Link className="button secondary" href={`/runs?run=${first.id}`}>
        {isZh ? "去审阅" : "Review"}
      </Link>
    </div>
  );
}
