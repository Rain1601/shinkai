import type { Locale } from "../../lib/i18n";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type InjectionHistoryProps = {
  events: RunEvent[];
  locale?: Locale;
};

type PairedInjection = {
  injectionId: string;
  intent: string;
  note: string;
  ts: number | null;
  ack?: {
    adopted: boolean;
    appliedTo: string;
    effectSummary: string;
  };
};

function intentLabel(intent: string, isZh: boolean): string {
  if (isZh) {
    if (intent === "guidance") return "提示";
    if (intent === "constraint") return "约束";
    if (intent === "correction") return "纠错";
    if (intent === "question") return "提问";
    return intent || "未知";
  }
  return intent || "unknown";
}

function appliedToLabel(appliedTo: string, isZh: boolean): string {
  if (isZh) {
    if (appliedTo === "frontier") return "下次前沿";
    if (appliedTo === "filter") return "筛选规则";
    if (appliedTo === "hypothesis") return "当前判断";
    if (appliedTo === "none") return "未生效";
    return appliedTo;
  }
  return appliedTo;
}

export function InjectionHistory({ events, locale = "zh" }: InjectionHistoryProps) {
  const isZh = locale === "zh";
  const pairs = new Map<string, PairedInjection>();
  for (const event of events) {
    if (event.type === "human_injection") {
      const injectionId = event.event_id ?? "";
      if (!injectionId) continue;
      pairs.set(injectionId, {
        injectionId,
        intent: String(event.data?.intent ?? "guidance"),
        note: String(event.data?.note ?? ""),
        ts: typeof event.ts === "number" ? event.ts : null,
      });
    } else if (event.type === "injection_acknowledged") {
      const injectionId = String(event.data?.injection_id ?? "");
      if (!injectionId) continue;
      const existing = pairs.get(injectionId);
      const ack = {
        adopted: Boolean(event.data?.adopted),
        appliedTo: String(event.data?.applied_to ?? "none"),
        effectSummary: String(event.data?.effect_summary ?? ""),
      };
      if (existing) {
        existing.ack = ack;
      } else {
        pairs.set(injectionId, {
          injectionId,
          intent: String(event.data?.intent ?? "guidance"),
          note: String(event.data?.note ?? ""),
          ts: typeof event.ts === "number" ? event.ts : null,
          ack,
        });
      }
    }
  }
  const items = Array.from(pairs.values()).sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));

  return (
    <section className="surface injection-history">
      <div className="panel-heading">
        <h2>{isZh ? "注入历史" : "Injection History"}</h2>
        <span className="label">{items.length}</span>
      </div>
      <p className="muted">
        {isZh
          ? "每条人工注入都会被 agent 在下一次循环边界处明确回应；这里显示意图、原文和采纳状态。"
          : "Every human injection is explicitly acknowledged by the agent at the next loop boundary."}
      </p>
      {items.length === 0 ? (
        <p className="muted">
          {isZh ? "暂无注入。" : "No injections yet."}
        </p>
      ) : null}
      <div className="injection-list">
        {items.map((item) => {
          const status = !item.ack
            ? "pending"
            : item.ack.adopted
              ? "adopted"
              : "ignored";
          const statusLabel = !item.ack
            ? isZh
              ? "等待 agent 回应"
              : "awaiting agent ack"
            : item.ack.adopted
              ? isZh
                ? "已采纳"
                : "adopted"
              : isZh
                ? "未生效"
                : "ignored";
          return (
            <article className={`injection-item injection-${status}`} key={item.injectionId}>
              <header>
                <span className="pill">{intentLabel(item.intent, isZh)}</span>
                <span className={`pill pill-${status}`}>{statusLabel}</span>
              </header>
              <p className="injection-note">{item.note || (isZh ? "（空）" : "(empty)")}</p>
              {item.ack ? (
                <p className="muted injection-effect">
                  <strong>{appliedToLabel(item.ack.appliedTo, isZh)}</strong>
                  {item.ack.effectSummary ? ` — ${item.ack.effectSummary}` : ""}
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
