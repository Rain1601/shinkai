import type { Locale } from "../../lib/i18n";
import {
  formatNumber,
  localizeDecision,
  localizeEventType,
  localizeText
} from "../../lib/i18n";

type AgentEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

type JudgmentPanelProps = {
  events: AgentEvent[];
  locale?: Locale;
};

export function JudgmentPanel({ events, locale = "zh" }: JudgmentPanelProps) {
  const isZh = locale === "zh";
  const themes = events.filter((event) => event.type === "theme_discovered");
  const judgments = events.filter((event) => event.type === "judgment_created");
  const candidates = events.filter((event) => event.type === "candidate_created");
  const scores = events.filter((event) => event.type === "candidate_scored");
  const evidence = events.filter((event) => event.type === "evidence_found");
  const reviews = events.filter((event) => event.type === "review_completed");
  const optimizations = events.filter((event) => event.type === "optimization_decision");
  const patches = events.filter((event) => String(event.type ?? "").endsWith("_patch_proposed"));

  return (
    <section className="surface judgment-panel">
      <div className="panel-heading">
        <h2>{isZh ? "自主产出" : "Autonomous Output"}</h2>
        <span className="label">{isZh ? "Agent 主导" : "Agent-led"}</span>
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "发现主题" : "Discovered Themes"}</span>
        {themes.length === 0 ? (
          <p className="muted">{isZh ? "暂无主题。" : "No themes surfaced yet."}</p>
        ) : null}
        {themes.map((event, index) => (
          <article className="judgment-item" key={`theme-${index}`}>
            <strong>{localizeText(event.data?.theme ?? (isZh ? "主题" : "Theme"), locale)}</strong>
            <p>{localizeText(event.data?.why ?? "", locale)}</p>
          </article>
        ))}
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "关键判断" : "Key Judgments"}</span>
        {judgments.length === 0 ? (
          <p className="muted">{isZh ? "暂无判断。" : "No judgments yet."}</p>
        ) : null}
        {judgments.map((event, index) => (
          <article className="judgment-item" key={`judgment-${index}`}>
            <strong>{judgmentTitle(event, locale)}</strong>
            <p>
              {isZh ? "置信度" : "confidence"}: {String(event.data?.confidence ?? "n/a")}
            </p>
          </article>
        ))}
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "候选队列" : "Candidate Queue"}</span>
        <div className="candidate-list">
          {candidates.length === 0 ? (
            <p className="muted">{isZh ? "暂无候选。" : "No candidates yet."}</p>
          ) : null}
          {candidates.map((event, index) => (
            <article className="candidate-chip" key={`candidate-${index}`}>
              <strong>{String(event.data?.ticker ?? (isZh ? "候选" : "Candidate"))}</strong>
              <span>
                {isZh
                  ? "执行 Q1 质量与 Q2 低覆盖度筛选"
                  : String(event.data?.next_action ?? "pending")}
              </span>
            </article>
          ))}
        </div>
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "评分" : "Scores"}</span>
        <div className="candidate-list">
          {scores.slice(-8).map((event, index) => (
            <article className="candidate-chip" key={`score-${index}`}>
              <strong>{String(event.data?.ticker ?? (isZh ? "评分" : "Score"))}</strong>
              <span>
                {String(event.data?.combined_score ?? "n/a")} ·{" "}
                {localizeDecision(event.data?.decision, locale)}
              </span>
              <span>
                Q1 {event.data?.q1_quality_pass ? (isZh ? "通过" : "pass") : isZh ? "观察" : "watch"} · Q2{" "}
                {event.data?.q2_underwater_pass ? (isZh ? "通过" : "pass") : isZh ? "观察" : "watch"}
              </span>
            </article>
          ))}
        </div>
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "来源证据" : "Source Evidence"}</span>
        {evidence.slice(-4).map((event, index) => (
          <article className="judgment-item" key={`evidence-${index}`}>
            <strong>
              {isZh
                ? `证据：${localizeText(event.data?.layer ?? "来源", locale)}`
                : String(event.data?.source_title ?? event.data?.layer ?? "Evidence")}
            </strong>
            <p>
              {event.data?.source_uri
                ? String(event.data.source_uri)
                : localizeText(event.data?.summary ?? (isZh ? "需要来源" : "needs source"), locale)}
            </p>
          </article>
        ))}
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "复盘 / 优化" : "Review / Optimize"}</span>
        {[...reviews, ...optimizations].slice(-4).map((event, index) => (
          <article className="judgment-item" key={`review-${index}`}>
            <strong>{localizeEventType(event.type, locale)}</strong>
            <p>{reviewSummary(event, locale)}</p>
          </article>
        ))}
      </div>

      <div className="judgment-section">
        <span className="label">{isZh ? "补丁建议" : "Patch Proposals"}</span>
        {patches.slice(-4).map((event, index) => (
          <article className="judgment-item" key={`patch-${index}`}>
            <strong>{localizeEventType(event.type, locale)}</strong>
            <p>{patchSummary(event, locale)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function judgmentTitle(event: AgentEvent, locale: Locale): string {
  if (locale === "en") return String(event.data?.judgment ?? "Judgment");
  return `${localizeText(event.data?.layer, locale) || "该层级"} 存在可研究的 AI 供应链二阶机会`;
}

function reviewSummary(event: AgentEvent, locale: Locale): string {
  if (locale === "en") {
    return String(event.data?.next_frontier ?? event.data?.policy_patch ?? event.data?.review_score ?? "");
  }
  if (event.type === "review_completed") {
    return `复盘分数：${formatNumber(event.data?.review_score)}；需要优化：${event.data?.optimize_required ? "是" : "否"}`;
  }
  return `下一前沿：${localizeText(event.data?.next_frontier, locale)}`;
}

function patchSummary(event: AgentEvent, locale: Locale): string {
  if (locale === "en") return String(event.data?.proposal ?? "");
  if (event.type === "memory_patch_proposed") return "建议写入研究记忆，保留该供应链前沿。";
  if (event.type === "filter_policy_patch_proposed") return "建议强化候选筛选规则：必须绑定瓶颈和来源证据。";
  if (event.type === "checklist_patch_proposed") return "建议更新公司深度分析清单：验证 AI 暴露是否直接、持久且改善利润率。";
  return "建议更新 agent 运行策略。";
}
