import type { Locale } from "../../lib/i18n";

type RunEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

type PlannerBadgeProps = {
  events: RunEvent[];
  locale?: Locale;
};

const SOURCE_STYLES: Record<string, { bg: string; color: string }> = {
  deepseek_llm_planner: { bg: "transparent", color: "#58A0BC" },
  fallback_after_reject: { bg: "transparent", color: "#B5BAC0" },
  deterministic_fallback: { bg: "transparent", color: "#7E8082" },
  force_llm_fail: { bg: "transparent", color: "#C46B62" },
};

function sourceLabel(source: string, isZh: boolean): string {
  if (isZh) {
    if (source === "deepseek_llm_planner") return "LLM 驱动";
    if (source === "fallback_after_reject") return "LLM 输出被拒,fallback";
    if (source === "deterministic_fallback") return "确定性 fallback";
    if (source === "force_llm_fail") return "force_llm 失败";
    return source;
  }
  if (source === "deepseek_llm_planner") return "LLM-driven";
  if (source === "fallback_after_reject") return "Fallback (LLM rejected)";
  if (source === "deterministic_fallback") return "Deterministic fallback";
  if (source === "force_llm_fail") return "Force-LLM fail";
  return source;
}

export function PlannerBadge({ events, locale = "zh" }: PlannerBadgeProps) {
  const isZh = locale === "zh";
  const proposals = events.filter((event) => event.type === "planner_proposals");
  const latest = proposals.length > 0 ? proposals[proposals.length - 1] : undefined;
  if (!latest) return null;
  const data = latest.data ?? {};
  const source = String(data.source ?? "deterministic_fallback");
  const rawCount = Number(data.raw_frontier_count ?? 0);
  const validatedCount = Number(data.validated_layer_count ?? 0);
  const rejectReason = data.reject_reason ? String(data.reject_reason) : "";
  const samples = Array.isArray(data.sample_layers)
    ? (data.sample_layers as unknown[]).map(String)
    : [];
  const style = SOURCE_STYLES[source] ?? SOURCE_STYLES.deterministic_fallback;
  const tooltip = [
    samples.length > 0
      ? `${isZh ? "层级示例" : "Sample layers"}: ${samples.join(" · ")}`
      : null,
    rejectReason
      ? `${isZh ? "拒绝原因" : "Reject"}: ${rejectReason}`
      : null,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <span
      className="planner-badge"
      style={{ background: style.bg, color: style.color }}
      title={tooltip}
    >
      <strong>{isZh ? "Planner" : "Planner"}: {sourceLabel(source, isZh)}</strong>
      <span className="planner-badge-counts">
        {validatedCount} / {rawCount}
      </span>
    </span>
  );
}
