"use client";

import { useState } from "react";
import type { Locale } from "../../lib/i18n";

type InjectPanelProps = {
  onInject?: (note: string, intent: string) => Promise<void> | void;
  onResolveCheckpoint?: (decision: "approve" | "reject" | "modify", note: string) => Promise<void> | void;
  disabled?: boolean;
  status?: string;
  locale?: Locale;
};

export function InjectPanel({
  onInject,
  onResolveCheckpoint,
  disabled,
  status,
  locale = "zh",
}: InjectPanelProps) {
  const isZh = locale === "zh";
  const [note, setNote] = useState("");
  const [intent, setIntent] = useState("guidance");
  const [submitting, setSubmitting] = useState(false);
  const awaitingCheckpoint = status === "awaiting_checkpoint" || status === "paused";

  async function handleInject() {
    if (!onInject || !note.trim()) return;
    setSubmitting(true);
    try {
      await onInject(note.trim(), intent);
      setNote("");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResolve(decision: "approve" | "reject" | "modify") {
    if (!onResolveCheckpoint) return;
    setSubmitting(true);
    try {
      await onResolveCheckpoint(decision, note.trim());
      setNote("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="surface inject-panel">
      <div className="panel-heading">
        <h2>{isZh ? "人工介入" : "Human Intervention"}</h2>
        {awaitingCheckpoint ? (
          <span className="pill warn">
            {isZh ? "等待审阅" : "Awaiting review"}
          </span>
        ) : null}
      </div>
      <p className="muted">
        {isZh
          ? "中间层接口：写入观察、约束或决策，立即进入 Agent 的事件流。"
          : "Middle-layer affordance: write guidance, constraints, or decisions directly into the agent's event log."}
      </p>
      <div className="inject-form">
        <label htmlFor="inject-intent">
          {isZh ? "意图" : "Intent"}
        </label>
        <select
          id="inject-intent"
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          disabled={disabled || submitting}
        >
          <option value="guidance">{isZh ? "提示/方向" : "Guidance"}</option>
          <option value="constraint">{isZh ? "约束" : "Constraint"}</option>
          <option value="correction">{isZh ? "纠错" : "Correction"}</option>
          <option value="question">{isZh ? "提问" : "Question"}</option>
        </select>
        <label htmlFor="inject-note">{isZh ? "内容" : "Note"}</label>
        <textarea
          id="inject-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={disabled || submitting}
          rows={3}
          placeholder={
            isZh
              ? "示例：忽略 example.com 的来源；重点验证 PowerCo 的 backlog 披露"
              : "Example: ignore example.com sources; focus on validating PowerCo backlog disclosure"
          }
        />
        <div className="control-grid">
          <button
            className="button"
            type="button"
            onClick={handleInject}
            disabled={disabled || submitting || !note.trim()}
          >
            {isZh ? "注入" : "Inject"}
          </button>
          {awaitingCheckpoint ? (
            <>
              <button
                className="button"
                type="button"
                onClick={() => handleResolve("approve")}
                disabled={disabled || submitting}
              >
                {isZh ? "批准" : "Approve"}
              </button>
              <button
                className="button secondary"
                type="button"
                onClick={() => handleResolve("modify")}
                disabled={disabled || submitting || !note.trim()}
              >
                {isZh ? "带注释继续" : "Modify"}
              </button>
              <button
                className="button danger"
                type="button"
                onClick={() => handleResolve("reject")}
                disabled={disabled || submitting}
              >
                {isZh ? "拒绝并终止" : "Reject"}
              </button>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
