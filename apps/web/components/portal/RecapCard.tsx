"use client";

import { useState } from "react";
import type { Locale } from "../../lib/i18n";
import { isImportantEvent } from "../../lib/useLastSeen";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type RecapCardProps = {
  events: RunEvent[];
  lastSeen: number;
  locale?: Locale;
};

function formatTime(ts: number, locale: Locale): string {
  if (!ts) return locale === "zh" ? "尚未访问" : "first visit";
  return new Date(ts * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RecapCard({ events, lastSeen, locale = "zh" }: RecapCardProps) {
  const isZh = locale === "zh";
  const [open, setOpen] = useState(true);

  if (!lastSeen) {
    return null;
  }

  const newEvents = events.filter(
    (event) => typeof event.ts === "number" && event.ts > lastSeen,
  );
  if (newEvents.length === 0) return null;

  const important = newEvents.filter((event) => isImportantEvent(event.type));

  const categoryCounts: Record<string, number> = {};
  for (const event of important) {
    const type = String(event.type ?? "");
    categoryCounts[type] = (categoryCounts[type] ?? 0) + 1;
  }

  const categoryOrder = [
    "checkpoint_raised",
    "critic_aggregated",
    "hypothesis_falsified",
    "human_injection",
    "injection_acknowledged",
    "memory_patch_proposed",
    "filter_policy_patch_proposed",
    "checklist_patch_proposed",
    "error",
  ];

  function categoryLabel(type: string): string {
    if (!isZh) return type;
    const map: Record<string, string> = {
      checkpoint_raised: "等待审阅",
      critic_aggregated: "评审汇总",
      hypothesis_falsified: "假设证伪",
      human_injection: "人工注入",
      injection_acknowledged: "注入回应",
      memory_patch_proposed: "记忆补丁",
      filter_policy_patch_proposed: "筛选补丁",
      checklist_patch_proposed: "清单补丁",
      error: "错误",
    };
    return map[type] ?? type;
  }

  return (
    <section className="surface recap-card">
      <header
        className="recap-card-header"
        onClick={() => setOpen((prev) => !prev)}
        role="button"
        tabIndex={0}
      >
        <div className="recap-card-summary">
          <strong>
            {isZh ? "上次访问后" : "Since last visit"} ·{" "}
            {formatTime(lastSeen, locale)}
          </strong>
          <span>
            {isZh
              ? `新增 ${newEvents.length} 个事件 · 重要 ${important.length}`
              : `${newEvents.length} new events · ${important.length} important`}
          </span>
        </div>
        <span className="recap-card-toggle">{open ? "▾" : "▸"}</span>
      </header>
      {open ? (
        <div className="recap-card-body">
          {important.length === 0 ? (
            <p className="muted">
              {isZh
                ? "无关键事件,仅普通过程事件。"
                : "No important events — only routine activity."}
            </p>
          ) : (
            <div className="recap-categories">
              {categoryOrder
                .filter((type) => categoryCounts[type])
                .map((type) => (
                  <span key={type} className="recap-category pill">
                    <strong>{categoryLabel(type)}</strong> ×{" "}
                    {categoryCounts[type]}
                  </span>
                ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
