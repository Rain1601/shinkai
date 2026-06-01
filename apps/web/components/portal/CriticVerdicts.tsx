import type { Locale } from "../../lib/i18n";

type RunEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

type CriticVerdictsProps = {
  dossierId: string;
  events: RunEvent[];
  locale?: Locale;
};

const VERDICT_COLORS: Record<string, string> = {
  endorse: "#1f7a3a",
  concerns: "#b27200",
  reject: "#a02633",
};

const VERDICT_BG: Record<string, string> = {
  endorse: "rgba(40, 167, 69, 0.12)",
  concerns: "rgba(255, 165, 0, 0.14)",
  reject: "rgba(220, 53, 69, 0.14)",
};

function verdictLabel(verdict: string, isZh: boolean): string {
  if (isZh) {
    if (verdict === "endorse") return "支持";
    if (verdict === "concerns") return "存疑";
    if (verdict === "reject") return "否决";
    return verdict;
  }
  return verdict;
}

function personaLabel(persona: string, isZh: boolean): string {
  if (isZh) {
    if (persona === "buffett") return "巴菲特式";
    if (persona === "short_seller") return "做空视角";
    if (persona === "auditor") return "审计视角";
    return persona;
  }
  if (persona === "short_seller") return "Short-seller";
  if (persona === "auditor") return "Auditor";
  if (persona === "buffett") return "Buffett";
  return persona;
}

export function CriticVerdicts({ dossierId, events, locale = "zh" }: CriticVerdictsProps) {
  const isZh = locale === "zh";
  const critiques = events.filter(
    (event) =>
      event.type === "critic_persona_critique" &&
      event.data?.dossier_id === dossierId,
  );
  const aggregatedEvent = events.find(
    (event) =>
      event.type === "critic_aggregated" && event.data?.dossier_id === dossierId,
  );
  if (critiques.length === 0 && !aggregatedEvent) return null;

  const aggregatedFinal = aggregatedEvent ? String(aggregatedEvent.data?.final ?? "") : "";
  const appliedPenalty = aggregatedEvent
    ? Number(aggregatedEvent.data?.applied_penalty ?? 0)
    : 0;

  return (
    <div className="critic-verdicts">
      <div className="critic-verdicts-header">
        <span className="label">{isZh ? "L2 评审" : "L2 Critics"}</span>
        {aggregatedFinal ? (
          <span
            className="pill"
            style={{
              background: VERDICT_BG[aggregatedFinal],
              color: VERDICT_COLORS[aggregatedFinal],
            }}
          >
            {isZh ? "汇总" : "Aggregated"}: {verdictLabel(aggregatedFinal, isZh)}
            {appliedPenalty < 0
              ? ` · ${isZh ? "置信扣减" : "Δconfidence"} ${appliedPenalty.toFixed(3)}`
              : ""}
          </span>
        ) : null}
      </div>
      <div className="critic-personas">
        {critiques.map((event, index) => {
          const persona = String(event.data?.persona ?? "");
          const verdict = String(event.data?.verdict ?? "");
          const rationale = String(event.data?.rationale ?? "");
          return (
            <div
              className="critic-persona"
              key={`${persona}-${index}`}
              style={{
                borderLeftColor: VERDICT_COLORS[verdict] ?? "#888",
                background: VERDICT_BG[verdict] ?? "transparent",
              }}
            >
              <strong>{personaLabel(persona, isZh)}</strong>
              <span style={{ color: VERDICT_COLORS[verdict] }}>
                {verdictLabel(verdict, isZh)}
              </span>
              <p>{rationale}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
