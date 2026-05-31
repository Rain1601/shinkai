"use client";

import { useEffect, useMemo, useState } from "react";
import type { Locale } from "../../lib/i18n";
import { localizeDecision, localizeText } from "../../lib/i18n";

type GraphNode = {
  id: string;
  type: string;
  label?: string;
  confidence?: number;
  tags?: string[];
  source_refs?: string[];
  data?: Record<string, unknown>;
};

type GraphEdge = {
  id: string;
  relation: string;
  from_node: string;
  to_node: string;
};

type Graph = {
  graph_id: string;
  run_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type GraphPanelProps = {
  anchor?: string;
  graphId?: string | null;
  runId?: string | null;
  locale?: Locale;
};

type LayerView = {
  frontier: GraphNode;
  bottleneck?: GraphNode;
  evidence?: GraphNode;
  candidates: GraphNode[];
};

type VisualNode = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  kind: "anchor" | "frontier" | "bottleneck" | "evidence" | "candidate";
  title: string;
  subtitle: string;
  meta?: string;
  ready?: boolean;
};

type VisualEdge = {
  id: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  kind: "primary" | "support" | "candidate";
};

type GraphRenderSpec = {
  schema: "shinkai.graph.render.v1";
  width: number;
  height: number;
  nodes: VisualNode[];
  edges: VisualEdge[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export function GraphPanel({ anchor, graphId, runId, locale = "zh" }: GraphPanelProps) {
  const isZh = locale === "zh";
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    fetch(`${API_URL}/api/v1/runs/${runId}/graph`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`graph ${response.status}`);
        return response.json();
      })
      .then((payload: Graph) => {
        setGraph(payload);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [runId, graphId]);

  const layers = useMemo(() => buildLayerView(graph), [graph]);
  const nodes = graph?.nodes ?? [];
  const candidateCount = nodes.filter((node) => node.tags?.includes("candidate")).length;
  const modeAQueued = nodes.filter((node) => node.tags?.includes("mode-a-queue")).length;

  return (
    <section className="surface panel-fill graph-panel">
      <div className="panel-heading">
        <h2>{isZh ? "研究图谱" : "Research Graph"}</h2>
        <span className="label">{graph?.graph_id ?? graphId ?? (isZh ? "无图谱" : "no graph")}</span>
      </div>

      <div className="graph-visual-shell">
        {layers.length === 0 ? (
          <p className="muted">{isZh ? "暂无图谱层级。" : "No graph layers yet."}</p>
        ) : (
          <GraphVisual anchor={anchor} layers={layers} locale={locale} />
        )}
      </div>

      <div className="graph-flow-legend" aria-hidden="true">
        <span>{isZh ? "共识巨头" : "Mega caps"}</span>
        <span>{isZh ? "瓶颈层级" : "Bottleneck"}</span>
        <span>{isZh ? "证据" : "Evidence"}</span>
        <span>{isZh ? "候选公司" : "Candidates"}</span>
      </div>

      <div className="graph-summary">
        <div className="graph-anchor">
          <span className="label">{isZh ? "研究锚点" : "Anchor"}</span>
          <strong>{localizeText(anchor ?? (isZh ? "锚点" : "Anchor"), locale)}</strong>
          <p>
            {isZh
              ? "从共识 AI 巨头向下拆解供应链瓶颈，再把每个瓶颈映射到可深度分析的候选公司。"
              : "Decompose consensus AI giants into supply-chain bottlenecks, then map each bottleneck to company-analysis candidates."}
          </p>
        </div>
        <div className="graph-stat-row">
          <GraphStat label={isZh ? "层级" : "Layers"} value={layers.length} />
          <GraphStat label={isZh ? "候选" : "Candidates"} value={candidateCount} />
          <GraphStat label={isZh ? "模式A" : "Mode A"} value={modeAQueued} />
        </div>
      </div>

      {error ? (
        <p className="muted">{isZh ? `图谱不可用：${error}` : `Graph unavailable: ${error}`}</p>
      ) : null}
    </section>
  );
}

function GraphStat({ label, value }: { label: string; value: number }) {
  return (
    <span>
      <strong>{value}</strong>
      {label}
    </span>
  );
}

function GraphVisual({
  anchor,
  layers,
  locale
}: {
  anchor?: string;
  layers: LayerView[];
  locale: Locale;
}) {
  const isZh = locale === "zh";
  const spec = buildVisualLayout(anchor, layers, locale);

  return (
    <div
      aria-label={isZh ? "研究图谱关系视图" : "Research graph relationship view"}
      className="graph-render-viewport"
      data-render-schema={spec.schema}
      role="img"
    >
      <div
        className="graph-render-canvas"
        style={{ height: spec.height, width: spec.width }}
      >
        {spec.edges.map((edge) => (
          <div
            className={`graph-render-edge ${edge.kind}`}
            key={edge.id}
            style={edgeStyle(edge)}
          />
        ))}
        {spec.nodes.map((node) => (
          <article
            className={`graph-render-node ${node.kind}${node.ready ? " ready" : ""}`}
            key={node.id}
            style={{ height: node.h, left: node.x, top: node.y, width: node.w }}
          >
            <span className="node-kicker">{nodeLabel(node.kind, locale)}</span>
            <strong className="node-title">{node.title}</strong>
            <span className="node-subtitle">{node.subtitle}</span>
            {node.meta ? <span className="node-meta">{node.meta}</span> : null}
          </article>
        ))}
      </div>
      <script
        className="graph-render-json"
        type="application/json"
        suppressHydrationWarning
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            schema: spec.schema,
            width: spec.width,
            height: spec.height,
            nodes: spec.nodes,
            edges: spec.edges
          })
        }}
      />
    </div>
  );
}

function edgeStyle(edge: VisualEdge) {
  const dx = edge.toX - edge.fromX;
  const dy = edge.toY - edge.fromY;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx);
  return {
    left: edge.fromX,
    top: edge.fromY,
    transform: `rotate(${angle}rad)`,
    width: length
  };
}

function buildLayerView(graph: Graph | null): LayerView[] {
  if (!graph) return [];
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const frontiers = graph.nodes.filter((node) => node.tags?.includes("frontier"));

  return frontiers.map((frontier) => {
    const bottleneck = graph.edges
      .filter((edge) => edge.relation === "decomposes_into" && edge.from_node === frontier.id)
      .map((edge) => nodeById.get(edge.to_node))
      .find((node): node is GraphNode => Boolean(node && node.type === "Claim"));

    const evidence = bottleneck
      ? graph.edges
          .filter((edge) => edge.relation === "supports" && edge.to_node === bottleneck.id)
          .map((edge) => nodeById.get(edge.from_node))
          .find((node): node is GraphNode => Boolean(node && node.type === "Evidence"))
      : undefined;

    const candidates = graph.edges
      .filter((edge) => edge.relation === "participates_in" && edge.to_node === frontier.id)
      .map((edge) => nodeById.get(edge.from_node))
      .filter((node): node is GraphNode => Boolean(node && node.tags?.includes("candidate")))
      .sort((a, b) => numberValue(b.data?.combined_score ?? b.confidence) - numberValue(a.data?.combined_score ?? a.confidence));

    return { frontier, bottleneck, evidence, candidates };
  });
}

function buildVisualLayout(
  anchor: string | undefined,
  layers: LayerView[],
  locale: Locale
): GraphRenderSpec {
  const width = 1120;
  const rowHeight = 190;
  const top = 42;
  const height = Math.max(580, top * 2 + layers.length * rowHeight);
  const anchorNode: VisualNode = {
    id: "anchor",
    x: 28,
    y: top + 30,
    w: 145,
    h: 96,
    kind: "anchor",
    title: localizeText(anchor ?? (locale === "zh" ? "研究锚点" : "Anchor"), locale),
    subtitle: locale === "zh" ? "从共识 AI 巨头出发" : "Start from consensus AI giants",
    meta: locale === "zh" ? "自主发现" : "Autonomous"
  };
  const nodes: VisualNode[] = [anchorNode];
  const edges: VisualEdge[] = [];

  layers.forEach((layer, index) => {
    const y = top + index * rowHeight;
    const seeds = arrayOfStrings(layer.frontier.data?.seed_giants).slice(0, 4).join(" / ");
    const frontier: VisualNode = {
      id: `frontier-${layer.frontier.id}`,
      x: 230,
      y: y + 34,
      w: 170,
      h: 88,
      kind: "frontier",
      title: localizeText(layer.frontier.label ?? "Layer", locale),
      subtitle: seeds,
      meta: locale === "zh" ? `第 ${index + 1} 层` : `Layer ${index + 1}`
    };
    const bottleneckText = String(layer.bottleneck?.data?.statement ?? layer.bottleneck?.label ?? "");
    const bottleneck: VisualNode = {
      id: `bottleneck-${layer.frontier.id}`,
      x: 470,
      y: y + 24,
      w: 190,
      h: 108,
      kind: "bottleneck",
      title: localizeText(layer.frontier.label ?? "Bottleneck", locale),
      subtitle: localizeText(bottleneckText, locale),
      meta: locale === "zh" ? "约束/瓶颈" : "Constraint"
    };
    const sourceKind = String(layer.evidence?.data?.source_kind ?? "");
    const needsSource = Boolean(layer.evidence?.data?.needs_real_source);
    const evidence: VisualNode = {
      id: `evidence-${layer.frontier.id}`,
      x: 710,
      y: y + 34,
      w: 130,
      h: 88,
      kind: "evidence",
      title: needsSource
        ? locale === "zh"
          ? "待补来源"
          : "Needs source"
        : locale === "zh"
          ? "来源支撑"
          : "Source-backed",
      subtitle: sourceKind || (locale === "zh" ? "Agent 推断" : "Agent inference"),
      meta: `${Math.round(numberValue(layer.evidence?.confidence) * 100)}%`
    };

    nodes.push(frontier, bottleneck, evidence);
    edges.push({
      id: `anchor-${frontier.id}`,
      fromX: anchorNode.x + anchorNode.w,
      fromY: anchorNode.y + anchorNode.h / 2,
      toX: frontier.x,
      toY: frontier.y + frontier.h / 2,
      kind: "primary"
    });
    edges.push({
      id: `${frontier.id}-${bottleneck.id}`,
      fromX: frontier.x + frontier.w,
      fromY: frontier.y + frontier.h / 2,
      toX: bottleneck.x,
      toY: bottleneck.y + bottleneck.h / 2,
      kind: "primary"
    });
    edges.push({
      id: `${bottleneck.id}-${evidence.id}`,
      fromX: bottleneck.x + bottleneck.w,
      fromY: bottleneck.y + bottleneck.h / 2,
      toX: evidence.x,
      toY: evidence.y + evidence.h / 2,
      kind: "support"
    });

    layer.candidates.slice(0, 4).forEach((candidate, candidateIndex) => {
      const quality = numberValue(candidate.data?.quality_score);
      const underwater = numberValue(candidate.data?.underwater_score);
      const score = numberValue(candidate.data?.combined_score ?? candidate.confidence);
      const ready = quality >= 0.65 && underwater >= 0.55 && score >= 0.62;
      const candidateNode: VisualNode = {
        id: `candidate-${candidate.id}`,
        x: 900,
        y: y + 4 + candidateIndex * 44,
        w: 160,
        h: 38,
        kind: "candidate",
        title: String(candidate.data?.ticker ?? candidate.label ?? "Candidate"),
        subtitle: String(candidate.data?.name ?? ""),
        meta: `${Math.round(score * 100)}% · ${localizeDecision(ready ? "queue_mode_a" : "watch_only", locale)}`,
        ready
      };
      nodes.push(candidateNode);
      edges.push({
        id: `${bottleneck.id}-${candidateNode.id}`,
        fromX: bottleneck.x + bottleneck.w,
        fromY: bottleneck.y + bottleneck.h / 2,
        toX: candidateNode.x,
        toY: candidateNode.y + candidateNode.h / 2,
        kind: ready ? "candidate" : "support"
      });
    });
  });

  return { schema: "shinkai.graph.render.v1", width, height, nodes, edges };
}

function nodeLabel(kind: VisualNode["kind"], locale: Locale): string {
  if (locale !== "zh") {
    return {
      anchor: "Anchor",
      frontier: "Layer",
      bottleneck: "Bottleneck",
      evidence: "Evidence",
      candidate: "Company"
    }[kind];
  }
  return {
    anchor: "研究锚点",
    frontier: "层级",
    bottleneck: "瓶颈",
    evidence: "证据",
    candidate: "公司"
  }[kind];
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
