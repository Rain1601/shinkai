"use client";

import { useEffect, useMemo, useState } from "react";
import type { Locale } from "../../lib/i18n";
import { formatNumber } from "../../lib/i18n";

type Evidence = {
  evidence_id: string;
  source_id: string;
  text: string;
  quote: string;
  summary: string;
  url: string;
  citation_url: string;
  kind: string;
  confidence: number;
  extracted_at: number;
  published_at: number | null;
};

type SourceRef = {
  source_id: string;
  type: string;
  tier: string;
  url: string;
  title: string;
  publisher: string;
  reliability: number;
  published_at: number | null;
  primary_source_flag: boolean;
};

type Claim = {
  claim_id: string;
  run_id: string;
  text: string;
  topic: string;
  status: string;
  verification: string;
  confidence: number;
  hypothesis_id: string | null;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  metadata: Record<string, unknown>;
};

type ConfidencePoint = {
  ts: number;
  confidence: number;
  delta: number;
  evidence_id: string;
  kind: string;
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
};

type ReasoningClaim = {
  claim: Claim;
  supporting_evidence: Evidence[];
  contradicting_evidence: Evidence[];
};

type ReasoningHypothesis = {
  hypothesis: Hypothesis;
  claims: ReasoningClaim[];
};

type ReasoningTree = {
  run_id: string;
  hypotheses: ReasoningHypothesis[];
  orphan_claims: ReasoningClaim[];
  sources: Record<string, SourceRef>;
};

type Selected =
  | { kind: "hypothesis"; id: string }
  | { kind: "claim"; id: string }
  | { kind: "evidence"; id: string }
  | null;

type ReasoningTreeViewProps = {
  runId: string | null;
  locale?: Locale;
  refreshSignal?: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";
const KIND_COLORS: Record<string, string> = {
  support: "#7AAA98",
  contradict: "#B85C57",
  human_correction: "#A0B5BD",
};
const SPARK_AXIS = "rgba(232,226,210,0.10)";
const SPARK_CURVE = "#4FA89B";

function Sparkline({ points }: { points: ConfidencePoint[] }) {
  const width = 280;
  const height = 68;
  const padding = 8;
  if (points.length === 0) return null;
  const xs = points.map(
    (_, i) => padding + (i / Math.max(1, points.length - 1)) * (width - 2 * padding),
  );
  const ys = points.map(
    (point) => padding + (1 - point.confidence) * (height - 2 * padding),
  );
  const pathD = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  return (
    <svg width={width} height={height} className="hypothesis-sparkline" role="img">
      <line
        x1={padding}
        y1={padding}
        x2={padding}
        y2={height - padding}
        stroke={SPARK_AXIS}
        strokeWidth={0.5}
      />
      <line
        x1={padding}
        y1={height - padding}
        x2={width - padding}
        y2={height - padding}
        stroke={SPARK_AXIS}
        strokeWidth={0.5}
      />
      <path d={pathD} fill="none" stroke={SPARK_CURVE} strokeWidth={1} />
      {points.map((point, i) => (
        <circle
          key={`${point.evidence_id}-${i}`}
          cx={xs[i]}
          cy={ys[i]}
          r={2.5}
          fill={KIND_COLORS[point.kind] ?? "#A0B5BD"}
        />
      ))}
    </svg>
  );
}

export function ReasoningTreeView({
  runId,
  locale = "zh",
  refreshSignal,
}: ReasoningTreeViewProps) {
  const isZh = locale === "zh";
  const [tree, setTree] = useState<ReasoningTree | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selected>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!runId) {
      setTree(null);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/runs/${runId}/reasoning-tree`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error(`${response.status}`);
        const data: ReasoningTree = await response.json();
        if (cancelled) return;
        setTree(data);
        setError(null);
        if (!selected && data.hypotheses.length > 0) {
          const firstHypId = data.hypotheses[0].hypothesis.hypothesis_id;
          setSelected({ kind: "hypothesis", id: firstHypId });
          setExpanded((prev) => new Set(prev).add(firstHypId));
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [runId, refreshSignal]);

  const flatEvidence: Record<string, Evidence> = useMemo(() => {
    if (!tree) return {};
    const out: Record<string, Evidence> = {};
    for (const hyp of tree.hypotheses) {
      for (const claim of hyp.claims) {
        for (const ev of [...claim.supporting_evidence, ...claim.contradicting_evidence]) {
          out[ev.evidence_id] = ev;
        }
      }
    }
    for (const claim of tree.orphan_claims) {
      for (const ev of [...claim.supporting_evidence, ...claim.contradicting_evidence]) {
        out[ev.evidence_id] = ev;
      }
    }
    return out;
  }, [tree]);

  if (!runId || !tree) {
    return (
      <section className="surface">
        <p className="muted">
          {error
            ? error
            : isZh
              ? "加载推理树中…"
              : "Loading reasoning tree…"}
        </p>
      </section>
    );
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectHypothesis(id: string) {
    setSelected({ kind: "hypothesis", id });
    setExpanded((prev) => new Set(prev).add(id));
  }
  function selectClaim(id: string) {
    setSelected({ kind: "claim", id });
  }
  function selectEvidence(id: string) {
    setSelected({ kind: "evidence", id });
  }

  return (
    <div className="reasoning-tree-view">
      <aside className="reasoning-tree-list">
        <div className="panel-heading">
          <h2>{isZh ? "推理树" : "Reasoning Tree"}</h2>
          <span className="label">{tree.hypotheses.length}</span>
        </div>
        {tree.hypotheses.map((node) => {
          const hyp = node.hypothesis;
          const isOpen = expanded.has(hyp.hypothesis_id);
          const isSelected =
            selected?.kind === "hypothesis" && selected.id === hyp.hypothesis_id;
          return (
            <div className="reasoning-tree-hypothesis" key={hyp.hypothesis_id}>
              <button
                type="button"
                className={`reasoning-tree-row depth-0 ${isSelected ? "active" : ""}`}
                onClick={() => {
                  selectHypothesis(hyp.hypothesis_id);
                  toggle(hyp.hypothesis_id);
                }}
              >
                <span className="reasoning-tree-toggle">{isOpen ? "▾" : "▸"}</span>
                <span className="reasoning-tree-label">
                  {hyp.layer || (isZh ? "假设" : "Hypothesis")}
                </span>
                <span className={`pill pill-state-${hyp.state}`}>
                  {hyp.state === "active"
                    ? isZh
                      ? "活跃"
                      : "active"
                    : hyp.state === "falsified"
                      ? isZh
                        ? "证伪"
                        : "falsified"
                      : isZh
                        ? "替换"
                        : "superseded"}
                </span>
                <span className="reasoning-tree-conf">
                  {formatNumber(hyp.confidence)}
                </span>
              </button>
              {isOpen ? (
                <div className="reasoning-tree-children">
                  {node.claims.map((resolved) => {
                    const claimId = resolved.claim.claim_id;
                    const isClaimOpen = expanded.has(claimId);
                    const isClaimSelected =
                      selected?.kind === "claim" && selected.id === claimId;
                    return (
                      <div key={claimId}>
                        <button
                          type="button"
                          className={`reasoning-tree-row depth-1 ${isClaimSelected ? "active" : ""}`}
                          onClick={() => {
                            selectClaim(claimId);
                            toggle(claimId);
                          }}
                        >
                          <span className="reasoning-tree-toggle">
                            {isClaimOpen ? "▾" : "▸"}
                          </span>
                          <span className="reasoning-tree-label">
                            {resolved.claim.text.slice(0, 80)}
                          </span>
                          <span className={`pill pill-claim-${resolved.claim.status}`}>
                            {resolved.claim.status}
                          </span>
                        </button>
                        {isClaimOpen ? (
                          <div className="reasoning-tree-children">
                            {resolved.supporting_evidence.map((ev) => (
                              <button
                                key={`s-${ev.evidence_id}`}
                                type="button"
                                className={`reasoning-tree-row depth-2 evidence-support ${selected?.kind === "evidence" && selected.id === ev.evidence_id ? "active" : ""}`}
                                onClick={() => selectEvidence(ev.evidence_id)}
                              >
                                <span className="reasoning-tree-toggle">✓</span>
                                <span className="reasoning-tree-label">
                                  {ev.summary || ev.text.slice(0, 60) || ev.evidence_id}
                                </span>
                              </button>
                            ))}
                            {resolved.contradicting_evidence.map((ev) => (
                              <button
                                key={`c-${ev.evidence_id}`}
                                type="button"
                                className={`reasoning-tree-row depth-2 evidence-contradict ${selected?.kind === "evidence" && selected.id === ev.evidence_id ? "active" : ""}`}
                                onClick={() => selectEvidence(ev.evidence_id)}
                              >
                                <span className="reasoning-tree-toggle">✗</span>
                                <span className="reasoning-tree-label">
                                  {ev.summary || ev.text.slice(0, 60) || ev.evidence_id}
                                </span>
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
        {tree.orphan_claims.length > 0 ? (
          <p className="muted small">
            {isZh
              ? `+ ${tree.orphan_claims.length} 个未关联假设的 claim`
              : `+ ${tree.orphan_claims.length} orphan claims`}
          </p>
        ) : null}
      </aside>
      <section className="reasoning-tree-detail surface">
        {selected?.kind === "hypothesis" ? (
          <HypothesisDetail
            node={
              tree.hypotheses.find((n) => n.hypothesis.hypothesis_id === selected.id)!
            }
            locale={locale}
          />
        ) : null}
        {selected?.kind === "claim" ? (
          <ClaimDetail
            resolved={(() => {
              for (const hyp of tree.hypotheses) {
                const claim = hyp.claims.find((c) => c.claim.claim_id === selected.id);
                if (claim) return claim;
              }
              return tree.orphan_claims.find((c) => c.claim.claim_id === selected.id)!;
            })()}
            sources={tree.sources}
            onSelectEvidence={selectEvidence}
            locale={locale}
          />
        ) : null}
        {selected?.kind === "evidence" ? (
          <EvidenceDetail
            evidence={flatEvidence[selected.id]}
            source={tree.sources[flatEvidence[selected.id]?.source_id]}
            locale={locale}
          />
        ) : null}
        {!selected ? (
          <p className="muted">
            {isZh ? "选择左侧节点查看详情。" : "Select a node to inspect."}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function HypothesisDetail({
  node,
  locale,
}: {
  node: ReasoningHypothesis;
  locale: Locale;
}) {
  const isZh = locale === "zh";
  const hyp = node.hypothesis;
  return (
    <div className="reasoning-detail-body">
      <div className="reasoning-detail-heading">
        <h3>{hyp.layer}</h3>
        <span className={`pill pill-state-${hyp.state}`}>{hyp.state}</span>
      </div>
      <p className="hypothesis-claim">{hyp.claim}</p>
      <div className="hypothesis-confidence-row">
        <span className="hypothesis-confidence-label">
          {isZh ? "置信度" : "Confidence"}
        </span>
        <strong className="hypothesis-confidence-value">
          {formatNumber(hyp.confidence)}
        </strong>
      </div>
      <Sparkline points={hyp.confidence_history} />
      <div className="hypothesis-legend">
        <span>
          <i style={{ background: KIND_COLORS.support }} />{" "}
          {isZh ? "支持" : "support"} ({hyp.supporting_evidence_ids.length})
        </span>
        <span>
          <i style={{ background: KIND_COLORS.contradict }} />{" "}
          {isZh ? "反对" : "contradict"} ({hyp.contradicting_evidence_ids.length})
        </span>
        <span>
          <i style={{ background: KIND_COLORS.human_correction }} />{" "}
          {isZh ? "人工" : "human"} (
          {hyp.confidence_history.filter((p) => p.kind === "human_correction").length}
          )
        </span>
      </div>
      {hyp.falsification_condition ? (
        <div className="hypothesis-falsification">
          <span className="label">{isZh ? "证伪条件" : "Falsification"}</span>
          <p>{hyp.falsification_condition}</p>
        </div>
      ) : null}
      <div className="muted small">
        {isZh ? "关联 claims" : "Linked claims"}: {node.claims.length}
      </div>
    </div>
  );
}

function ClaimDetail({
  resolved,
  sources,
  onSelectEvidence,
  locale,
}: {
  resolved: ReasoningClaim;
  sources: Record<string, SourceRef>;
  onSelectEvidence: (id: string) => void;
  locale: Locale;
}) {
  const isZh = locale === "zh";
  const claim = resolved.claim;
  return (
    <div className="reasoning-detail-body">
      <div className="reasoning-detail-heading">
        <h3>{isZh ? "论点" : "Claim"}</h3>
        <span className={`pill pill-claim-${claim.status}`}>{claim.status}</span>
      </div>
      <p className="claim-text">{claim.text}</p>
      <div className="claim-meta">
        <span>
          {isZh ? "验证" : "Verification"}: {claim.verification}
        </span>
        <span>
          {isZh ? "置信" : "Confidence"}: {formatNumber(claim.confidence)}
        </span>
        {claim.hypothesis_id ? (
          <code>{claim.hypothesis_id}</code>
        ) : (
          <span className="muted">{isZh ? "无关联假设" : "no hypothesis"}</span>
        )}
      </div>
      <EvidenceList
        title={isZh ? `支持(${resolved.supporting_evidence.length})` : `Supporting (${resolved.supporting_evidence.length})`}
        items={resolved.supporting_evidence}
        sources={sources}
        onSelect={onSelectEvidence}
        kind="support"
        locale={locale}
      />
      <EvidenceList
        title={isZh ? `反对(${resolved.contradicting_evidence.length})` : `Contradicting (${resolved.contradicting_evidence.length})`}
        items={resolved.contradicting_evidence}
        sources={sources}
        onSelect={onSelectEvidence}
        kind="contradict"
        locale={locale}
      />
    </div>
  );
}

function EvidenceList({
  title,
  items,
  sources,
  onSelect,
  kind,
  locale,
}: {
  title: string;
  items: Evidence[];
  sources: Record<string, SourceRef>;
  onSelect: (id: string) => void;
  kind: "support" | "contradict";
  locale: Locale;
}) {
  const isZh = locale === "zh";
  if (items.length === 0) return null;
  return (
    <div className="claim-evidence-block">
      <span className="label">{title}</span>
      <ul>
        {items.map((ev) => {
          const src = sources[ev.source_id];
          return (
            <li key={`${kind}-${ev.evidence_id}`}>
              <button
                type="button"
                className="link-button"
                onClick={() => onSelect(ev.evidence_id)}
              >
                {ev.summary || ev.text.slice(0, 80) || ev.evidence_id}
              </button>
              {src ? (
                <span className="muted small">
                  {" "}
                  · {src.tier} · {isZh ? "可信" : "reliab"} {formatNumber(src.reliability)}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function EvidenceDetail({
  evidence,
  source,
  locale,
}: {
  evidence?: Evidence;
  source?: SourceRef;
  locale: Locale;
}) {
  const isZh = locale === "zh";
  if (!evidence) {
    return <p className="muted">{isZh ? "未找到证据" : "evidence not found"}</p>;
  }
  return (
    <div className="reasoning-detail-body">
      <div className="reasoning-detail-heading">
        <h3>{isZh ? "证据" : "Evidence"}</h3>
        <span className="pill">{evidence.kind}</span>
      </div>
      {source ? (
        <div className="evidence-source-card">
          <strong>{source.title || source.url || source.source_id}</strong>
          <div className="muted small">
            {source.tier} · {source.type} ·{" "}
            {isZh ? "可信" : "reliability"} {formatNumber(source.reliability)}
            {source.primary_source_flag ? ` · ${isZh ? "一手" : "primary"}` : ""}
          </div>
          {source.url ? (
            <a className="link-button" href={source.url} target="_blank" rel="noreferrer">
              {source.url}
            </a>
          ) : null}
        </div>
      ) : null}
      {evidence.quote ? (
        <blockquote className="evidence-quote">{evidence.quote}</blockquote>
      ) : null}
      {evidence.summary ? <p>{evidence.summary}</p> : null}
      {evidence.text ? <p className="muted small">{evidence.text}</p> : null}
      <div className="muted small">
        {isZh ? "证据 ID" : "Evidence id"}: <code>{evidence.evidence_id}</code>
      </div>
    </div>
  );
}
