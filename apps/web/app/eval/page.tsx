"use client";

import { useEffect, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";
import { localizeStatus, localizeText } from "../../lib/i18n";

type Run = {
  id: string;
  anchor: string;
  status: string;
  events: Array<{ type?: string }>;
};

type EvalFinding = {
  severity: string;
  target_ref: string;
  message: string;
};

type EvalReport = {
  run_id: string;
  process_score: number | null;
  evidence_score: number | null;
  reasoning_score: number | null;
  discovery_score: number | null;
  claim_score: number | null;
  source_quality_score: number | null;
  candidate_dossier_score: number | null;
  findings: EvalFinding[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function EvalPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const isZh = locale === "zh";

  useEffect(() => {
    const storedLocale = window.localStorage.getItem("shinkai.locale");
    if (storedLocale === "zh" || storedLocale === "en") setLocale(storedLocale);
    fetch(`${API_URL}/api/v1/runs`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`runs ${response.status}`);
        return response.json();
      })
      .then((payload: Run[]) => {
        setRuns(payload);
        const completed = payload.find((run) => run.status === "completed") ?? payload[0];
        if (completed) setSelectedRunId(completed.id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    fetch(`${API_URL}/api/v1/eval/runs/${selectedRunId}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`eval ${response.status}`);
        return response.json();
      })
      .then((payload: EvalReport) => {
        setReport(payload);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedRunId]);

  function changeLocale(nextLocale: Locale) {
    setLocale(nextLocale);
    window.localStorage.setItem("shinkai.locale", nextLocale);
  }

  return (
    <PortalShell
      active="eval"
      actions={
        <div className="segmented-control" aria-label={isZh ? "语言" : "Language"}>
          <button
            aria-pressed={locale === "zh"}
            className={locale === "zh" ? "active" : ""}
            onClick={() => changeLocale("zh")}
            type="button"
          >
            中文
          </button>
          <button
            aria-pressed={locale === "en"}
            className={locale === "en" ? "active" : ""}
            onClick={() => changeLocale("en")}
            type="button"
          >
            EN
          </button>
        </div>
      }
      locale={locale}
      subtitle={
        isZh
          ? "从运行过程、证据、论点、来源质量和公司档案完整度评估 Agent。"
          : "Trace-native process, evidence, claim, source, and dossier evaluation."
      }
      title={isZh ? "评测报告" : "Eval Reports"}
    >
      <section className="grid">
        <div className="surface stack">
          <span className="label">{isZh ? "运行" : "Run"}</span>
          <h2>{isZh ? "被评测运行" : "Evaluated Run"}</h2>
          {runs.length === 0 ? <p className="muted">{isZh ? "暂无运行。" : "No runs yet."}</p> : null}
          <div className="run-list">
            {runs.map((run) => (
              <button
                className={selectedRunId === run.id ? "run-card active" : "run-card"}
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                type="button"
              >
                <strong>{localizeText(run.anchor, locale)}</strong>
                <span>
                  {localizeStatus(run.status, locale)} ·{" "}
                  {isZh ? `${run.events.length} 条事件` : `${run.events.length} events`}
                </span>
              </button>
            ))}
          </div>
          {error ? <p className="muted">{error}</p> : null}
        </div>

        <div className="surface stack">
          <span className="label">{isZh ? "分数" : "Scores"}</span>
          <h2>{isZh ? "轨迹评测" : "Trace Eval"}</h2>
          {report ? (
            <div className="eval-score-grid">
              <Score label={isZh ? "过程" : "Process"} value={report.process_score} />
              <Score label={isZh ? "证据覆盖" : "Evidence"} value={report.evidence_score} />
              <Score label={isZh ? "推理" : "Reasoning"} value={report.reasoning_score} />
              <Score label={isZh ? "发现" : "Discovery"} value={report.discovery_score} />
              <Score label={isZh ? "论点可信" : "Claims"} value={report.claim_score} />
              <Score
                label={isZh ? "来源质量" : "Sources"}
                value={report.source_quality_score}
              />
              <Score
                label={isZh ? "公司档案" : "Dossiers"}
                value={report.candidate_dossier_score}
              />
            </div>
          ) : (
            <p className="muted">{isZh ? "请选择一个已完成运行。" : "Select a completed run."}</p>
          )}
        </div>
      </section>

      <section className="surface stack eval-findings">
        <div className="panel-heading">
          <h2>{isZh ? "评测发现" : "Findings"}</h2>
          <span className="label">{report?.findings.length ?? 0}</span>
        </div>
        {report?.findings.length === 0 ? (
          <p className="muted">{isZh ? "暂无发现。" : "No findings."}</p>
        ) : null}
        {report?.findings.map((finding, index) => (
          <article className="judgment-item" key={`${finding.target_ref}-${index}`}>
            <strong>{finding.severity}</strong>
            <p>{localizeFinding(finding.message, locale)}</p>
          </article>
        ))}
      </section>
    </PortalShell>
  );
}

function localizeFinding(message: string, locale: Locale): string {
  if (locale !== "zh") return message;
  if (message === "No supply-chain layer was expanded.") return "没有扩展任何供应链层级。";
  if (message === "Candidate coverage is thin for the expanded frontier count.") {
    return "相对已扩展前沿，候选公司覆盖偏薄。";
  }
  if (message === "Some evidence nodes still need source-backed verification.") {
    return "部分证据节点仍缺少可追溯来源验证。";
  }
  if (message === "Not every loop produced a self-iteration patch proposal.") {
    return "不是每一轮都产生了自我迭代补丁。";
  }
  if (message === "Not every scored candidate has a candidate claim node.") {
    return "部分已评分候选公司缺少候选论点节点。";
  }
  if (message === "Not every scored candidate has an open underwriting question.") {
    return "部分已评分候选公司缺少后续深度分析问题。";
  }
  if (message === "No candidate has been promoted to an initial thesis yet.") {
    return "尚无候选公司被提升为初始研究 thesis。";
  }
  if (message === "Some claim nodes are missing verification metadata.") {
    return "部分论点节点缺少校验元数据。";
  }
  if (message.includes("claims lack sufficient source support")) {
    return message.replace("claims lack sufficient source support.", "个论点缺少足够来源支撑。");
  }
  if (message.includes("supported claims still lack a primary source")) {
    return message.replace("supported claims still lack a primary source.", "个已支持论点仍缺少一手来源。");
  }
  if (message.includes("claims have refuting evidence")) {
    return message.replace("claims have refuting evidence.", "个论点存在反证。");
  }
  if (message.includes("claims depend on stale sources")) {
    return message.replace("claims depend on stale sources.", "个论点依赖过期来源。");
  }
  if (message === "The run found evidence but no primary-source-backed evidence.") {
    return "运行找到了证据，但没有一手来源支撑的证据。";
  }
  if (message === "Not every scored candidate has a company dossier.") {
    return "部分已评分候选公司缺少公司深度档案。";
  }
  if (message === "At least one investment decision was made without passing Mode A checks.") {
    return "至少一个投资决策没有通过 Mode A 检查。";
  }
  return message;
}

function Score({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="autonomy-card accent">
      <span className="label">{label}</span>
      <strong className="numeric">{value === null ? "n/a" : Math.round(value * 100)}</strong>
    </div>
  );
}
