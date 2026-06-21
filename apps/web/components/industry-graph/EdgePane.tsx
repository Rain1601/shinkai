"use client";

import Link from "next/link";
import type { GraphEdge, GraphNode, GraphPayload } from "./cytoscape-helpers";
import { type Locale } from "../../lib/i18n";

type Props = {
  edge: GraphEdge;
  graph: GraphPayload;
  subjectMap?: Map<string, string>;
  locale: Locale;
  onClear: () => void;
};

function fmtPct(v: number | null | undefined): string {
  if (typeof v !== "number") return "—";
  return `${Math.round(v * 100)}%`;
}

function evidenceLabel(t: string | null | undefined, locale: Locale): string {
  if (t === "hard_data") return locale === "zh" ? "◆ hard" : "◆ hard";
  if (t === "soft_inference") return locale === "zh" ? "◇ soft" : "◇ soft";
  return "—";
}

function relationLabel(t: string, locale: Locale): string {
  const en = t.replace("_", " ");
  if (locale === "zh") {
    if (t === "supplies_to") return "供应";
    if (t === "competes_with") return "竞争";
    if (t === "themed_under") return "归属主题";
    if (t === "produces") return "生产";
    if (t === "part_of") return "组成";
  }
  return en;
}

export function EdgePane({ edge, graph, subjectMap, locale, onClear }: Props) {
  const isZh = locale === "zh";
  const src = graph.nodes.find((n) => n.id === edge.source) ?? null;
  const tgt = graph.nodes.find((n) => n.id === edge.target) ?? null;

  // Year-keyed weight rows sorted ascending. Demo uses three slots for
  // supplies_to (buyer/seller/lock-in) and two for competes_with.
  const years = Object.keys(edge.wbp ?? {}).sort();
  const isSupplies = edge.type === "supplies_to";
  const isCompetes = edge.type === "competes_with";

  function renderNodeBlock(n: GraphNode | null, role: "src" | "tgt") {
    if (!n) return null;
    const subjectId = subjectMap?.get(n.id);
    const eyebrow = role === "src"
      ? (isZh ? "源 · source" : "Source")
      : (isZh ? "目标 · target" : "Target");
    return (
      <section className="ig-edge-node">
        <span className="ig-edge-node-eyebrow">{eyebrow}</span>
        <h4 className="ig-edge-node-name">
          {subjectId ? (
            <Link href={`/industry-graph/${encodeURIComponent(subjectId)}`}>
              {n.label}
              <span className="ig-edge-node-go"> ↗</span>
            </Link>
          ) : (
            n.label
          )}
        </h4>
        <dl className="ig-edge-node-meta">
          <dt>id</dt>
          <dd>{n.id}</dd>
          {n.layer ? (
            <>
              <dt>{isZh ? "层位" : "stratum"}</dt>
              <dd>{n.layer}</dd>
            </>
          ) : null}
        </dl>
        {n.desc ? <p className="ig-edge-node-desc">{n.desc}</p> : null}
      </section>
    );
  }

  return (
    <aside className="ig-anchor-pane ig-edge-pane">
      <div className="ig-edge-topbar">
        <span className="ig-anchor-eyebrow">
          {isZh ? "关系 · relation" : "Relation"}
        </span>
        <button type="button" className="live-pill" onClick={onClear}>
          {isZh ? "← 返回 anchor" : "← back to anchor"}
        </button>
      </div>

      <span className={`ig-edge-type-pill type-${edge.type}`}>
        {relationLabel(edge.type, locale)}
      </span>

      <h2 className="ig-edge-arrow">
        <span>{src?.label ?? edge.source}</span>
        <span className="arrow">→</span>
        <span>{tgt?.label ?? edge.target}</span>
      </h2>

      {renderNodeBlock(src, "src")}
      {renderNodeBlock(tgt, "tgt")}

      {years.length > 0 ? (
        <section className="ig-edge-weights">
          <div className="ig-rel-head-row">
            <h3>{isZh ? "权重 · 历年" : "Weights · by year"}</h3>
            <span className="ig-rel-count">{years.length}</span>
          </div>
          <table className="ig-edge-weights-table">
            <thead>
              <tr>
                <th>{isZh ? "年份" : "year"}</th>
                {isSupplies ? (
                  <>
                    <th>{isZh ? "买方占比" : "buyer spend"}</th>
                    <th>{isZh ? "卖方收入" : "seller rev"}</th>
                    <th>{isZh ? "锁定度" : "lock-in"}</th>
                  </>
                ) : isCompetes ? (
                  <>
                    <th>{isZh ? "直接重叠" : "overlap"}</th>
                    <th>{isZh ? "份额 Δ" : "share Δ"}</th>
                  </>
                ) : (
                  <th>{isZh ? "强度" : "weight"}</th>
                )}
              </tr>
            </thead>
            <tbody>
              {years.map((y) => {
                const w = edge.wbp[y] ?? [];
                if (isSupplies) {
                  return (
                    <tr key={y}>
                      <td className="y">{y}</td>
                      <td>{fmtPct(w[0])}</td>
                      <td>{fmtPct(w[1])}</td>
                      <td>{fmtPct(w[2])}</td>
                    </tr>
                  );
                }
                if (isCompetes) {
                  const delta = typeof w[1] === "number" ? w[1] : 0;
                  return (
                    <tr key={y}>
                      <td className="y">{y}</td>
                      <td>{fmtPct(w[0])}</td>
                      <td>
                        {delta > 0 ? "+" : ""}
                        {(delta * 100).toFixed(0)}%
                      </td>
                    </tr>
                  );
                }
                return (
                  <tr key={y}>
                    <td className="y">{y}</td>
                    <td>{fmtPct(w[0])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : (
        <p className="muted" style={{ marginTop: 14 }}>
          {isZh ? "暂无年度权重数据。" : "No per-period weights recorded."}
        </p>
      )}

      <section className="ig-edge-evidence">
        <div className="ig-rel-head-row">
          <h3>{isZh ? "证据" : "Evidence"}</h3>
        </div>
        <dl className="ig-anchor-dl">
          <dt>{isZh ? "类型" : "type"}</dt>
          <dd
            className={`ig-edge-evid ${edge.evidence_type === "soft_inference" ? "soft" : "hard"}`}
          >
            {evidenceLabel(edge.evidence_type, locale)}
          </dd>
          {edge.confidence != null ? (
            <>
              <dt>{isZh ? "置信" : "confidence"}</dt>
              <dd>{Math.round((edge.confidence ?? 0) * 100)}%</dd>
            </>
          ) : null}
          {edge.evidence_ref ? (
            <>
              <dt>{isZh ? "来源" : "source"}</dt>
              <dd>{edge.evidence_ref}</dd>
            </>
          ) : null}
          <dt>{isZh ? "关系 id" : "edge id"}</dt>
          <dd>{edge.id}</dd>
        </dl>
      </section>
    </aside>
  );
}
