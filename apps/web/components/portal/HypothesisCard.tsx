"use client";

import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";
import { formatNumber } from "../../lib/i18n";

type ConfidencePoint = {
  ts: number;
  confidence: number;
  delta: number;
  evidence_id: string;
  kind: "support" | "contradict" | "human_correction";
  method: string;
};

type Hypothesis = {
  hypothesis_id: string;
  run_id: string;
  layer: string;
  claim: string;
  confidence: number;
  state: "active" | "falsified" | "superseded";
  falsification_condition: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  confidence_history: ConfidencePoint[];
  superseded_by_id: string | null;
};

type HypothesisCardProps = {
  runId: string | null;
  locale?: Locale;
  refreshSignal?: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

const KIND_COLORS: Record<ConfidencePoint["kind"], string> = {
  support: "#94B0A0",
  contradict: "#C46B62",
  human_correction: "#B5BAC0",
};

const SPARK_LINE_AXIS = "rgba(226,227,224,0.10)";
const SPARK_LINE_GUIDE = "rgba(226,227,224,0.05)";
const SPARK_LINE_CURVE = "#58A0BC";

function Sparkline({ points }: { points: ConfidencePoint[] }) {
  const width = 300;
  const height = 88;
  const padding = 8;
  if (points.length === 0) return null;
  const xs = points.map(
    (_, i) => padding + (i / Math.max(1, points.length - 1)) * (width - 2 * padding)
  );
  const ys = points.map(
    (point) => padding + (1 - point.confidence) * (height - 2 * padding)
  );
  const pathD = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  return (
    <svg
      className="hypothesis-sparkline"
      width={width}
      height={height}
      role="img"
      aria-label="confidence trajectory"
    >
      <line
        x1={padding}
        y1={padding}
        x2={padding}
        y2={height - padding}
        stroke={SPARK_LINE_AXIS}
        strokeWidth={0.5}
      />
      <line
        x1={padding}
        y1={height - padding}
        x2={width - padding}
        y2={height - padding}
        stroke={SPARK_LINE_AXIS}
        strokeWidth={0.5}
      />
      <line
        x1={padding}
        y1={padding + (height - 2 * padding) * 0.5}
        x2={width - padding}
        y2={padding + (height - 2 * padding) * 0.5}
        stroke={SPARK_LINE_GUIDE}
        strokeWidth={0.5}
      />
      <path d={pathD} fill="none" stroke={SPARK_LINE_CURVE} strokeWidth={1} />
      {points.map((point, i) => (
        <circle
          key={`${point.evidence_id}-${i}`}
          cx={xs[i]}
          cy={ys[i]}
          r={2.5}
          fill={KIND_COLORS[point.kind]}
        />
      ))}
    </svg>
  );
}

function stateLabel(state: Hypothesis["state"], isZh: boolean): string {
  if (isZh) {
    if (state === "active") return "活跃";
    if (state === "falsified") return "已证伪";
    return "已替换";
  }
  return state;
}

export function HypothesisCard({ runId, locale = "zh", refreshSignal }: HypothesisCardProps) {
  const isZh = locale === "zh";
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setHypotheses([]);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/runs/${runId}/hypotheses`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`${response.status}`);
        const data: Hypothesis[] = await response.json();
        if (cancelled) return;
        setHypotheses(data);
        setActiveIndex((current) => Math.min(current, Math.max(0, data.length - 1)));
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [runId, refreshSignal]);

  if (!runId || hypotheses.length === 0) {
    return (
      <section className="surface hypothesis-card">
        <div className="panel-heading">
          <h2>{isZh ? "当前假设" : "Current Hypothesis"}</h2>
          <span className="label">{isZh ? "未形成" : "none"}</span>
        </div>
        <p className="muted">
          {isZh
            ? "Agent 还没有产出可追踪的假设。运行启动后,每个层级会在这里出现一张卡。"
            : "No tracked hypotheses yet. Each layer's hypothesis will appear here once the run starts."}
        </p>
        {error ? <p className="muted">{error}</p> : null}
      </section>
    );
  }

  const safeIndex = Math.min(activeIndex, hypotheses.length - 1);
  const active = hypotheses[safeIndex];
  const supportCount = active.supporting_evidence_ids.length;
  const contradictCount = active.contradicting_evidence_ids.length;
  const correctionCount = active.confidence_history.filter(
    (point) => point.kind === "human_correction"
  ).length;

  return (
    <section
      className="surface hypothesis-card"
      id={`hypothesis-${active.hypothesis_id}`}
    >
      <div className="panel-heading">
        <h2>{isZh ? "当前假设" : "Current Hypothesis"}</h2>
        <span className={`pill pill-state-${active.state}`}>{stateLabel(active.state, isZh)}</span>
      </div>
      {hypotheses.length > 1 ? (
        <div className="hypothesis-pager">
          <button
            className="button secondary"
            onClick={() => setActiveIndex((i) => Math.max(0, i - 1))}
            disabled={safeIndex === 0}
            type="button"
          >
            ‹
          </button>
          <span>
            {safeIndex + 1} / {hypotheses.length}
          </span>
          <button
            className="button secondary"
            onClick={() => setActiveIndex((i) => Math.min(hypotheses.length - 1, i + 1))}
            disabled={safeIndex === hypotheses.length - 1}
            type="button"
          >
            ›
          </button>
        </div>
      ) : null}
      <p className="hypothesis-claim">{active.claim}</p>
      <div className="hypothesis-confidence-row">
        <span className="hypothesis-confidence-label">
          {isZh ? "当前置信度" : "Confidence"}
        </span>
        <strong className="hypothesis-confidence-value">
          {formatNumber(active.confidence)}
        </strong>
      </div>
      <Sparkline points={active.confidence_history} />
      <div className="hypothesis-legend">
        <span><i style={{ background: KIND_COLORS.support }} /> {isZh ? "支持" : "support"} ({supportCount})</span>
        <span><i style={{ background: KIND_COLORS.contradict }} /> {isZh ? "反对" : "contradict"} ({contradictCount})</span>
        <span><i style={{ background: KIND_COLORS.human_correction }} /> {isZh ? "人工纠正" : "human"} ({correctionCount})</span>
      </div>
      {active.falsification_condition ? (
        <div className="hypothesis-falsification">
          <span className="label">{isZh ? "证伪条件" : "Falsification"}</span>
          <p>{active.falsification_condition}</p>
        </div>
      ) : null}
      <div className="hypothesis-meta">
        <span>{isZh ? "层级" : "Layer"}: {active.layer}</span>
        <code>{active.hypothesis_id}</code>
      </div>
    </section>
  );
}
