import type { Locale } from "../../lib/i18n";
import {
  formatNumber,
  localizeDecision,
  localizeEventType,
  localizeMode,
  localizeText
} from "../../lib/i18n";

type EventStreamProps = {
  events: Array<{
    event_id?: string;
    type?: string;
    ts?: number;
    data?: Record<string, unknown>;
  }>;
  locale?: Locale;
};

export function EventStream({ events, locale = "zh" }: EventStreamProps) {
  const isZh = locale === "zh";
  return (
    <section className="surface panel-fill">
      <div className="panel-heading">
        <h2>{isZh ? "自主运行记录" : "Autonomy Feed"}</h2>
        <span className="label">{isZh ? `${events.length} 条事件` : `${events.length} events`}</span>
      </div>
      <div className="event-list">
        {events.length === 0 ? (
          <p className="muted">{isZh ? "暂无事件。" : "No events yet."}</p>
        ) : null}
        {events.map((event, index) => (
          <article className="event-row" key={event.event_id ?? `${event.type ?? "event"}-${index}`}>
            <div className="event-type">{localizeEventType(event.type, locale)}</div>
            <div className="event-body">{summarizeEvent(event, locale)}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function summarizeEvent(
  event: { type?: string; data?: Record<string, unknown> },
  locale: Locale
): string {
  const data = event.data;
  if (!data) return locale === "zh" ? "无载荷" : "No payload";
  if (locale === "zh") return summarizeZh(event.type, data);
  if (typeof data.text === "string") return data.text;
  if (typeof data.theme === "string") return data.theme;
  if (typeof data.layer === "string" && typeof data.bottleneck === "string") {
    return `${data.layer}: ${data.bottleneck}`;
  }
  if (typeof data.next_frontier === "string") return `Next frontier: ${data.next_frontier}`;
  if (typeof data.judgment === "string") return data.judgment;
  if (typeof data.claim === "string") return data.claim;
  if (typeof data.source_uri === "string") return `Evidence: ${data.source_uri}`;
  if (typeof data.ticker === "string") return `${data.ticker}: ${String(data.reason ?? "")}`;
  if (typeof data.proposal === "string") return data.proposal;
  if (typeof data.decision === "string") return `Decision: ${data.decision}`;
  if (typeof data.task === "string") return data.task;
  if (typeof data.summary === "string") return data.summary;
  if (typeof data.title === "string") return data.title;
  if (typeof data.status === "string") return data.status;
  return JSON.stringify(data);
}

function summarizeZh(type: string | undefined, data: Record<string, unknown>): string {
  const layer = localizeText(data.layer, "zh");
  if (type === "run_start") {
    return `运行已创建：${localizeMode(data.mode, "zh")} · ${localizeText(data.anchor, "zh")}`;
  }
  if (type === "run_recovered") return "运行已从持久化状态恢复。";
  if (type === "plan") {
    return "计划已生成：按“规划、扩展、证据、评分、复盘、优化”循环执行。";
  }
  if (type === "tool_call") return `调用工具：${String(data.name ?? "tool")}`;
  if (type === "tool_result") {
    return `工具返回：${String(data.name ?? "tool")} · ${data.ok ? "成功" : "失败"}`;
  }
  if (type === "frontier_selected") {
    return `选择前沿：${localizeText(data.frontier, "zh")} · 优先级 ${formatNumber(data.priority)}`;
  }
  if (type === "frontier_reprioritized") {
    return `前沿重排：${localizeText(data.frontier, "zh")} · ${localizeDecision(data.action, "zh") || String(data.action ?? "")}`;
  }
  if (type === "role_step_completed") {
    return `角色完成：${String(data.role ?? "agent")} · ${String(data.step ?? "")}`;
  }
  if (type === "supply_chain_layer_started") {
    return `开始扩展层级：${layer}`;
  }
  if (type === "frontier_expanded" || type === "theme_discovered") {
    const body = localizeText(data.bottleneck ?? data.why ?? data.theme, "zh");
    return `${layer || localizeText(data.theme, "zh")}：${body}`;
  }
  if (type === "evidence_found") {
    if (typeof data.source_uri === "string" && data.source_uri) {
      return `找到证据来源：${data.source_uri}`;
    }
    return `记录证据缺口：${layer}`;
  }
  if (type === "claim_created") return `创建论点：${localizeText(data.claim, "zh")}`;
  if (type === "claim_validated") {
    return `校验论点：${String(data.status ?? "unknown")} · 独立来源 ${String(data.independent_source_count ?? 0)}`;
  }
  if (type === "judgment_created") {
    return `形成判断：${layer || "该层级"} 可能存在被低估的 AI 供应链二阶机会。`;
  }
  if (type === "candidate_created") {
    return `发现候选公司：${String(data.ticker ?? "候选")} · ${layer}`;
  }
  if (type === "candidate_scored") {
    return `候选评分：${String(data.ticker ?? "候选")} · 综合 ${formatNumber(data.combined_score)} · ${localizeDecision(data.decision, "zh")}`;
  }
  if (type === "company_deep_analysis_completed") {
    return `公司深度分析完成：${String(data.ticker ?? "候选")} · ${String(data.status ?? "")}`;
  }
  if (type === "company_dossier_created") {
    return `公司档案：${String(data.ticker ?? "候选")} · ${localizeDecision(data.decision, "zh")}`;
  }
  if (type === "review_completed") {
    return `复盘完成：${layer} · 分数 ${formatNumber(data.review_score)}`;
  }
  if (type === "optimization_decision") {
    return `优化决策：${localizeDecision(data.decision, "zh")} · 下一前沿：${localizeText(data.next_frontier, "zh")}`;
  }
  if (String(type ?? "").endsWith("_patch_proposed")) {
    return `提出改进补丁：${localizeEventType(type, "zh")}`;
  }
  if (type === "research_task_created") return `创建研究任务：${localizeText(data.task, "zh")}`;
  if (type === "graph_delta") {
    return `研究图更新：新增 ${String(data.nodes_added ?? 0)} 个节点、${String(data.edges_added ?? 0)} 条边。`;
  }
  if (type === "eval_completed") {
    return `评测完成：过程 ${formatNumber(data.process_score)}，证据 ${formatNumber(data.evidence_score)}，发现 ${formatNumber(data.discovery_score)}。`;
  }
  if (type === "budget_exhausted") {
    return `预算耗尽：${String(data.budget ?? "budget")} · 上限 ${String(data.max_tool_calls ?? "")}`;
  }
  if (type === "child_run_created") {
    return `创建下一轮自主迭代：${localizeText(data.child_anchor, "zh")}`;
  }
  if (type === "done") return `运行完成：${localizeText(data.status, "zh")}`;
  if (type === "error") return `错误：${String(data.message ?? data.error ?? "未知错误")}`;
  return localizeText(data.summary ?? data.title ?? data.status ?? JSON.stringify(data), "zh");
}
