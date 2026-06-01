"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";

type Patch = {
  patch_id: string;
  type: string;
  proposal: string;
  requires_human_approval: boolean;
  run_id: string | null;
  ts: number | null;
  loop_index: number | null;
  decision: "pending" | "accepted" | "rejected" | "modified";
  decided_at: number | null;
  note: string;
};

type PatchInboxProps = {
  locale: Locale;
};

type StatusFilter = "pending" | "accepted" | "rejected" | "all";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

function typeLabel(type: string, isZh: boolean): string {
  if (type === "memory_patch_proposed") return isZh ? "记忆补丁" : "memory patch";
  if (type === "filter_policy_patch_proposed")
    return isZh ? "筛选补丁" : "filter patch";
  if (type === "checklist_patch_proposed")
    return isZh ? "清单补丁" : "checklist patch";
  return type;
}

function statusLabel(status: StatusFilter, isZh: boolean): string {
  if (status === "pending") return isZh ? "待处理" : "Pending";
  if (status === "accepted") return isZh ? "已接受" : "Accepted";
  if (status === "rejected") return isZh ? "已拒绝" : "Rejected";
  return isZh ? "全部" : "All";
}

function formatTime(ts: number | null, locale: Locale): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PatchInbox({ locale }: PatchInboxProps) {
  const isZh = locale === "zh";
  const [patches, setPatches] = useState<Patch[]>([]);
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const response = await fetch(
        `${API_URL}/api/v1/actions/patches/inbox?status=${status}`,
        { cache: "no-store" },
      );
      if (!response.ok) return;
      setPatches(await response.json());
    } catch {
      // silent
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, 6000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function decide(
    patchId: string,
    decision: "accept" | "reject" | "modify",
  ) {
    setBusy(patchId);
    try {
      await fetch(`${API_URL}/api/v1/actions/patches/${patchId}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, note: "" }),
      });
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="surface patch-inbox">
      <div className="panel-heading">
        <h2>{isZh ? "补丁收件箱" : "Patch Inbox"}</h2>
        <div className="patch-inbox-tabs">
          {(["pending", "accepted", "rejected", "all"] as StatusFilter[]).map(
            (option) => (
              <button
                key={option}
                type="button"
                className={status === option ? "active" : ""}
                onClick={() => setStatus(option)}
              >
                {statusLabel(option, isZh)}
              </button>
            ),
          )}
        </div>
      </div>
      {patches.length === 0 ? (
        <p className="muted patch-inbox-empty">
          {isZh
            ? "暂无补丁。Agent 反思后会在这里堆积。"
            : "Inbox is empty. The agent's reflections appear here."}
        </p>
      ) : (
        <div className="patch-inbox-list">
          {patches.map((patch) => (
            <article className="patch-row" key={patch.patch_id}>
              <header>
                <div>
                  <span className="pill">{typeLabel(patch.type, isZh)}</span>
                  {patch.run_id ? (
                    <Link
                      className="link-button"
                      href={`/runs/${patch.run_id}?tab=cockpit`}
                    >
                      #{patch.run_id.slice(0, 8)}
                    </Link>
                  ) : null}
                </div>
                <span className="label">{formatTime(patch.ts, locale)}</span>
              </header>
              <p>{patch.proposal}</p>
              {patch.decision === "pending" ? (
                <div className="patch-row-actions">
                  <button
                    type="button"
                    className="button"
                    disabled={busy === patch.patch_id}
                    onClick={() => decide(patch.patch_id, "accept")}
                  >
                    {isZh ? "接受" : "Accept"}
                  </button>
                  <button
                    type="button"
                    className="button danger"
                    disabled={busy === patch.patch_id}
                    onClick={() => decide(patch.patch_id, "reject")}
                  >
                    {isZh ? "拒绝" : "Reject"}
                  </button>
                </div>
              ) : (
                <div className="patch-row-status">
                  <span className={`pill pill-${patch.decision}`}>
                    {patch.decision}
                  </span>
                  {patch.decided_at ? (
                    <span className="label">
                      {formatTime(patch.decided_at, locale)}
                    </span>
                  ) : null}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
