import type { Locale } from "../../lib/i18n";
import { formatNumber } from "../../lib/i18n";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type EvalTabProps = {
  events: RunEvent[];
  locale: Locale;
};

type ScoreSpec = {
  key: string;
  zh: string;
  en: string;
  description_zh: string;
  description_en: string;
};

const SCORES: ScoreSpec[] = [
  {
    key: "process_score",
    zh: "过程",
    en: "Process",
    description_zh: "前沿计划与角色推进的完整性",
    description_en: "Completeness of frontier planning and role progression",
  },
  {
    key: "evidence_score",
    zh: "证据",
    en: "Evidence",
    description_zh: "证据数量与一手来源覆盖",
    description_en: "Evidence count and primary-source coverage",
  },
  {
    key: "reasoning_score",
    zh: "推理",
    en: "Reasoning",
    description_zh: "判断链路的连贯性",
    description_en: "Coherence of the judgment chain",
  },
  {
    key: "claim_score",
    zh: "论点",
    en: "Claims",
    description_zh: "论点的支持/反对独立来源数",
    description_en: "Independent support/refute source counts",
  },
  {
    key: "source_quality_score",
    zh: "来源质量",
    en: "Source Quality",
    description_zh: "来源 tier 分布与可靠度",
    description_en: "Source tier distribution and reliability",
  },
  {
    key: "candidate_dossier_score",
    zh: "档案完整度",
    en: "Dossier",
    description_zh: "公司档案的字段覆盖与决策一致性",
    description_en: "Dossier field coverage and decision consistency",
  },
];

export function EvalTab({ events, locale }: EvalTabProps) {
  const isZh = locale === "zh";
  const evalEvents = events.filter((event) => event.type === "eval_completed");
  const latest = evalEvents.length > 0 ? evalEvents[evalEvents.length - 1] : undefined;

  return (
    <div className="eval-tab">
      <section className="surface">
        <div className="panel-heading">
          <h2>{isZh ? "评测得分" : "Evaluation"}</h2>
          <span className="label">
            {latest ? (isZh ? "已完成" : "completed") : isZh ? "未运行" : "pending"}
          </span>
        </div>
        {!latest ? (
          <p className="muted">
            {isZh
              ? "运行结束后会输出过程、证据、推理、论点、来源质量与档案完整度的六维评分。"
              : "After completion, six dimensions are scored: process, evidence, reasoning, claims, source quality, and dossier."}
          </p>
        ) : (
          <div className="eval-grid">
            {SCORES.map((score) => {
              const value = latest.data?.[score.key];
              return (
                <article className="eval-card" key={score.key}>
                  <span className="label">{isZh ? score.zh : score.en}</span>
                  <strong>{formatNumber(value)}</strong>
                  <small>{isZh ? score.description_zh : score.description_en}</small>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
