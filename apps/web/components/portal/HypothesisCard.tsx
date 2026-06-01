import type { Locale } from "../../lib/i18n";
import { formatNumber, localizeText } from "../../lib/i18n";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type HypothesisCardProps = {
  events: RunEvent[];
  locale?: Locale;
};

export function HypothesisCard({ events, locale = "zh" }: HypothesisCardProps) {
  const isZh = locale === "zh";
  const judgments = events.filter((event) => event.type === "judgment_created");
  const latest = judgments.length > 0 ? judgments[judgments.length - 1] : undefined;

  if (!latest) {
    return (
      <section className="surface hypothesis-card">
        <div className="panel-heading">
          <h2>{isZh ? "当前假设" : "Current Hypothesis"}</h2>
          <span className="label">{isZh ? "未形成" : "none"}</span>
        </div>
        <p className="muted">
          {isZh
            ? "Agent 还没有产出可追踪的判断。运行启动后会显示当前正在跟踪的假设。"
            : "The agent has not produced a trackable judgment yet. Once a run starts, the live hypothesis will appear here."}
        </p>
      </section>
    );
  }

  const judgment = localizeText(latest.data?.judgment ?? "", locale);
  const layer = localizeText(latest.data?.layer ?? "", locale);
  const confidence = latest.data?.confidence;
  const hypothesisId = String(latest.data?.hypothesis_id ?? "");
  const totalUpdates = judgments.filter(
    (event) => String(event.data?.hypothesis_id ?? "") === hypothesisId
  ).length;

  return (
    <section className="surface hypothesis-card">
      <div className="panel-heading">
        <h2>{isZh ? "当前假设" : "Current Hypothesis"}</h2>
        <span className="label hypothesis-confidence">
          {isZh ? "置信" : "Conf"} {formatNumber(confidence)}
        </span>
      </div>
      <p className="hypothesis-judgment">{judgment}</p>
      <div className="hypothesis-meta">
        {layer ? <span>{isZh ? "层级" : "Layer"}: {layer}</span> : null}
        {hypothesisId ? <code>{hypothesisId}</code> : null}
        <span>
          {isZh ? `已更新 ${totalUpdates} 次` : `${totalUpdates} update${totalUpdates === 1 ? "" : "s"}`}
        </span>
      </div>
    </section>
  );
}
