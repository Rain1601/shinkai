"use client";

import cytoscape from "cytoscape";
import type { Core, EdgeSingular, NodeSingular } from "cytoscape";
import { useEffect, useRef } from "react";
import {
  classifyRoles,
  colorForRole,
  computePositions,
  cssVar,
  type ComputedPositions,
  type GraphEdge,
  type GraphNode,
  type GraphPayload,
  LAYER_LABEL,
  type Role,
  strongestWeight,
} from "./cytoscape-helpers";

type RailEntry = {
  klass: "buyer" | "anchor" | "competitor" | "layer";
  label: string;
  count: number;
  virtualY: number;
};

const H_VIRT = 1100;

const MORPH_DURATION = 650;
const FADE_DURATION = 260;

type Props = {
  payload: GraphPayload | null;
  anchorId: string;
  showOrphans?: boolean;
  showLabels?: boolean;
  onNodeClick?: (id: string) => void;
  onEdgeClick?: (edge: GraphEdge) => void;
  onBackgroundClick?: () => void;
  onNodeDoubleClick?: (id: string) => void;
  // Entity id → Subject id, for the "linkable" affordance + dbltap navigation.
  subjectMap?: Map<string, string>;
};

export function SubjectGraph({
  payload,
  anchorId,
  showOrphans = false,
  showLabels = true,
  onNodeClick,
  onEdgeClick,
  onBackgroundClick,
  onNodeDoubleClick,
  subjectMap,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const railEntriesRef = useRef<RailEntry[]>([]);
  // Layer-band Y per node id, kept fresh by every render so drag snap-back
  // uses the latest strata positions even after a morph.
  const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  // Latest payload-derived callbacks so the cytoscape event closures (bound
  // once on first render) always see current props without re-binding.
  const callbacksRef = useRef({
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeDoubleClick,
  });
  callbacksRef.current = {
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeDoubleClick,
  };
  const subjectMapRef = useRef<Map<string, string> | undefined>(subjectMap);
  subjectMapRef.current = subjectMap;
  const payloadRef = useRef<GraphPayload | null>(payload);
  payloadRef.current = payload;

  useEffect(() => {
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, []);

  function computeRailEntries(
    visibleNodes: GraphNode[],
    roles: Map<string, Role>,
    layoutOut: ComputedPositions,
  ): RailEntry[] {
    const entries: RailEntry[] = [];
    const buyerCount = visibleNodes.filter((n) => roles.get(n.id) === "buyer").length;
    if (buyerCount > 0) {
      entries.push({ klass: "buyer", label: "Buyers", count: buyerCount, virtualY: H_VIRT * 0.14 });
    }
    entries.push({ klass: "anchor", label: "Anchor", count: 1, virtualY: H_VIRT * 0.4 });
    const compCount = visibleNodes.filter((n) => roles.get(n.id) === "competitor").length;
    if (compCount > 0) {
      entries.push({ klass: "competitor", label: "Competes", count: compCount, virtualY: H_VIRT * 0.32 });
    }
    for (const layer of layoutOut.supplierLayers) {
      const y = layoutOut.layerYByName.get(layer)!;
      const cnt = visibleNodes.filter(
        (n) => roles.get(n.id) === "supplier" && (n.layer ?? "other") === layer,
      ).length;
      entries.push({
        klass: "layer",
        label: LAYER_LABEL[layer] ?? layer,
        count: cnt,
        virtualY: y,
      });
    }
    return entries;
  }

  // ---- Highlight helpers (used by strata-row hover + neighborhood hover)
  function highlightLayerNodes(layerKey: string) {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      const isAnchor = n.data("isAnchor");
      const role = n.data("role");
      const layer = (n.data("raw") as GraphNode | undefined)?.layer ?? null;
      // Match strata rail entries: anchor row matches the anchor node,
      // buyer / competitor / specific supply layers match by role + layer.
      const matches =
        (layerKey === "anchor" && isAnchor) ||
        (layerKey === "buyer" && role === "buyer") ||
        (layerKey === "competitor" && role === "competitor") ||
        (role === "supplier" && (layer ?? "other") === layerKey);
      if (matches) n.removeClass("layer-dim");
      else n.addClass("layer-dim");
    });
  }
  function clearLayerHighlight() {
    cyRef.current?.nodes().removeClass("layer-dim");
  }

  function syncRail() {
    const cy = cyRef.current;
    const rail = railRef.current;
    const wrap = wrapRef.current;
    if (!cy || !rail || !wrap) return;
    const wrapBox = wrap.getBoundingClientRect();
    const pan = cy.pan();
    const z = cy.zoom();
    rail.innerHTML = railEntriesRef.current
      .map((r) => {
        const screenY = r.virtualY * z + pan.y;
        if (screenY < 8 || screenY > wrapBox.height - 8) return "";
        // layerKey: for supplier layer rows we want the actual layer string
        // (e.g. "memory"); for buyer / competitor / anchor we use the klass.
        const layerKey =
          r.klass === "layer"
            ? Object.entries(LAYER_LABEL).find(([, lbl]) => lbl === r.label)?.[0] ??
              r.label.toLowerCase().replace(/\s+/g, "_")
            : r.klass;
        return `<div class="ig-strata-row ig-strata-${r.klass}" style="top:${screenY}px;" data-layer="${layerKey}">${r.label}<span class="count">${r.count}</span></div>`;
      })
      .join("");
    // Re-attach hover listeners after each rail rebuild.
    rail.querySelectorAll<HTMLDivElement>(".ig-strata-row[data-layer]").forEach((el) => {
      const layerKey = el.dataset.layer ?? "";
      el.addEventListener("mouseenter", () => highlightLayerNodes(layerKey));
      el.addEventListener("mouseleave", clearLayerHighlight);
    });
  }

  useEffect(() => {
    if (!containerRef.current || !payload) return;
    const roles = classifyRoles(payload, anchorId);

    const visibleNodes = payload.nodes.filter(
      (n) => showOrphans || n.kind === "Company" || n.id === anchorId,
    );
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = payload.edges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
    );

    const layoutOut = computePositions(visibleNodes, roles, visibleEdges, anchorId);
    const { positions } = layoutOut;
    positionsRef.current = positions;
    railEntriesRef.current = computeRailEntries(visibleNodes, roles, layoutOut);

    // Edge widths: many seed relations carry no weight data (wbp empty), so
    // a naïve weight→width map collapses everything to the 0.6 px baseline.
    // Push the baseline up so edges are always visible, and scale generously
    // when weights ARE present.
    const maxW = Math.max(...visibleEdges.map(strongestWeight), 0.001);
    const hasAnyWeight = maxW > 0.01;
    const sMap = subjectMapRef.current;
    const cyNodes = visibleNodes.map((n) => {
      const role = roles.get(n.id) ?? "other";
      const isAnchor = role === "anchor";
      const data: Record<string, unknown> = {
        id: n.id,
        label: n.label,
        kind: n.kind,
        role,
        color: colorForRole(role),
        raw: n,
      };
      if (isAnchor) data.isAnchor = true;
      // linkable = double-click navigates to that Company's Subject detail.
      if (!isAnchor && sMap?.has(n.id)) data.linkable = true;
      return { data, position: positions.get(n.id) };
    });
    const cyEdges = visibleEdges.map((e) => {
      const w = strongestWeight(e);
      const normWidth = hasAnyWeight
        ? 1.4 + 4.6 * (w / maxW)
        : 1.6; // flat fallback when seed data carries no weights
      return {
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          weight: w,
          normWidth,
          raw: e,
        },
      };
    });

    const surface = cssVar("--abyss-1");
    const ink = cssVar("--pearl");
    const teal = cssVar("--teal");
    const warn = cssVar("--warn");
    const hairBright = cssVar("--hair-bright");

    const style: cytoscape.StylesheetStyle[] = [
      {
        selector: "node",
        style: {
          "background-color": surface,
          "background-opacity": 1,
          "border-width": 1.8,
          "border-color": "data(color)",
          label: "data(label)",
          "font-family": "Newsreader, Songti SC, Georgia, serif",
          "font-size": 11,
          "font-weight": 400,
          color: ink,
          "text-valign": "center",
          "text-halign": "center",
          "text-wrap": "wrap",
          "text-max-width": "78px",
          width: 60,
          height: 60,
          shape: "ellipse",
        },
      },
      {
        selector: "node[isAnchor]",
        style: {
          width: 112,
          height: 112,
          "border-width": 5,
          "border-color": cssVar("--role-anchor"),
          "background-color": cssVar("--role-anchor"),
          "background-opacity": 0.18,
          "font-family": "Fraunces, Songti SC, Georgia, serif",
          "font-size": 17,
          "font-weight": 600,
          color: cssVar("--pearl"),
          "text-outline-color": cssVar("--abyss"),
          "text-outline-width": 1.5,
        },
      },
      {
        selector: "node[role='buyer'], node[role='supplier']",
        style: { width: 64, height: 64 },
      },
      { selector: "node[role='competitor']", style: { width: 56, height: 56 } },
      {
        selector: "node[role='related'], node[role='other']",
        style: { width: 40, height: 40, "font-size": 9.5, "text-max-width": "64px" },
      },
      {
        selector: "node[kind = 'Bottleneck']",
        style: { shape: "diamond", "border-color": cssVar("--danger") },
      },
      {
        selector: "node[kind = 'KeyDataPoint']",
        style: { shape: "triangle", "border-color": cssVar("--warn") },
      },
      {
        selector: "node[kind = 'InvestmentThesis']",
        style: { shape: "round-rectangle", "border-color": cssVar("--teal") },
      },
      {
        selector: "node[kind = 'Source']",
        style: {
          shape: "rectangle",
          width: 24,
          height: 24,
          "border-color": cssVar("--pearl-dim"),
        },
      },
      {
        selector: "edge",
        style: {
          width: "data(normWidth)",
          "line-color": hairBright,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "target-arrow-color": hairBright,
          "arrow-scale": 0.9,
          opacity: 0.7,
        },
      },
      {
        selector: "edge[type = 'supplies_to']",
        style: { "line-color": teal, "target-arrow-color": teal, opacity: 0.8 },
      },
      {
        selector: "edge[type = 'competes_with']",
        style: {
          "line-color": warn,
          "target-arrow-color": warn,
          "line-style": "dashed",
          opacity: 0.7,
        },
      },
      {
        selector: "edge[type = 'themed_under']",
        style: {
          "line-color": cssVar("--role-buyer"),
          "target-arrow-color": cssVar("--role-buyer"),
          opacity: 0.4,
        },
      },
      {
        selector: ".selected",
        style: { "border-width": 3.6, "border-color": teal, "z-index": 99 },
      },
      {
        selector: "edge.selected",
        style: { width: 4, "line-color": teal, "target-arrow-color": teal, opacity: 1 },
      },
      { selector: ".dimmed", style: { opacity: 0.18 } },
      // Layer-dim — distinct from .dimmed so strata-rail hover and node hover
      // don't compound.
      { selector: "node.layer-dim", style: { opacity: 0.14 } },
      // Node hover — neighborhood mode: hovered node gets a brighter ring,
      // its edges read as "hi" (slightly opaque + thicker), all the rest get
      // .dimmed via JS so they fade out of focus.
      {
        selector: "node.hovered",
        style: {
          "border-width": 3.2,
          "border-color": teal,
          "z-index": 50,
        },
      },
      {
        selector: "edge.edge-hovered",
        style: {
          width: 3.2,
          opacity: 1,
          "z-index": 51,
        },
      },
      // Endpoint highlight when an edge is hovered or selected — both
      // endpoints of the focused edge get this ring.
      {
        selector: "node.endpoint-hi",
        style: {
          "border-width": 2.6,
          "border-color": teal,
        },
      },
      // Linkable nodes — slightly brighter border + pointer cursor (the
      // dbltap affordance). Anchor never gets linkable.
      {
        selector: "node[linkable]",
        style: {
          "border-color": cssVar("--teal-line"),
          "border-style": "double",
        },
      },
    ];

    // Morph path: when the cy instance already exists, update in place.
    if (cyRef.current) {
      morphInto(cyRef.current, cyNodes, cyEdges, positions);
      setTimeout(syncRail, MORPH_DURATION + 40);
      return;
    }

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: { nodes: cyNodes, edges: cyEdges },
      style,
      layout: {
        name: "preset",
        positions: (node: NodeSingular | string) => {
          const id = typeof node === "string" ? node : node.id();
          return positions.get(id)!;
        },
      },
      minZoom: 0.25,
      maxZoom: 2.4,
    });

    if (!showLabels) {
      cyRef.current.nodes().forEach((n) => {
        if (!n.data("isAnchor")) n.style("label", "");
      });
    }

    // ---- Interaction wiring (bound once on first render) ----
    const cy = cyRef.current;

    // Tooltip overlay: created lazily on first edge hover so it lives inside
    // the wrapper and inherits canvas positioning.
    function ensureTooltip(): HTMLDivElement {
      if (!tooltipRef.current && wrapRef.current) {
        const el = document.createElement("div");
        el.className = "ig-edge-tooltip";
        el.style.display = "none";
        wrapRef.current.appendChild(el);
        tooltipRef.current = el;
      }
      return tooltipRef.current!;
    }

    function buildTooltipHtml(edge: EdgeSingular): string {
      const raw = edge.data("raw") as GraphEdge | undefined;
      const srcLabel = edge.source().data("label") || edge.source().id();
      const tgtLabel = edge.target().data("label") || edge.target().id();
      const type = String(edge.data("type") || "").replace("_", " ");
      const years = Object.keys(raw?.wbp ?? {}).sort();
      const latest = years[years.length - 1];
      const w = latest && raw ? raw.wbp[latest] : null;
      const fmt = (v: number | undefined | null) =>
        typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
      const rows: string[] = [];
      if (w && edge.data("type") === "supplies_to") {
        rows.push(
          `<div class="tip-row"><span>buyer spend</span><span class="v">${fmt(w[0])}</span></div>`,
          `<div class="tip-row"><span>seller revenue</span><span class="v">${fmt(w[1])}</span></div>`,
          `<div class="tip-row"><span>lock-in</span><span class="v">${fmt(w[2])}</span></div>`,
        );
      } else if (w && edge.data("type") === "competes_with") {
        const delta = w[1] ?? 0;
        rows.push(
          `<div class="tip-row"><span>direct overlap</span><span class="v">${fmt(w[0])}</span></div>`,
          `<div class="tip-row"><span>share Δ</span><span class="v">${delta > 0 ? "+" : ""}${(delta * 100).toFixed(0)}%</span></div>`,
        );
      }
      if (raw?.evidence_type) {
        rows.push(
          `<div class="tip-row"><span>evidence</span><span class="v">${raw.evidence_type === "hard_data" ? "◆ hard" : "◇ soft"}</span></div>`,
        );
      }
      if (raw?.confidence != null) {
        rows.push(
          `<div class="tip-row"><span>confidence</span><span class="v">${Math.round((raw.confidence ?? 0) * 100)}%</span></div>`,
        );
      }
      const yearLabel = latest ? ` · ${latest}` : "";
      let html = `<div class="tip-head">${srcLabel}<span class="tip-arrow">→</span>${tgtLabel}</div>`;
      html += `<div class="tip-type">${type}${yearLabel}</div>`;
      html += rows.join("");
      if (raw?.evidence_ref) {
        html += `<div class="tip-foot">${raw.evidence_ref}</div>`;
      }
      return html;
    }

    function positionTooltip(evt: cytoscape.EventObject) {
      const tip = ensureTooltip();
      const wrap = wrapRef.current;
      if (!wrap) return;
      const pos = (evt as unknown as { renderedPosition?: { x: number; y: number }; position?: { x: number; y: number } })
        .renderedPosition ?? (evt as unknown as { position?: { x: number; y: number } }).position;
      if (!pos) return;
      const wrapRect = wrap.getBoundingClientRect();
      let x = pos.x + 14;
      let y = pos.y + 14;
      if (x + 260 > wrapRect.width) x = pos.x - 270;
      if (y + 180 > wrapRect.height) y = pos.y - 190;
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    }

    // ---- node hover: neighborhood highlight ----
    cy.on("mouseover", "node", (evt) => {
      const n = evt.target as NodeSingular;
      if (n.data("kind") === "SupplyLayer") return;
      const neigh = n.closedNeighborhood();
      const rest = cy.elements().difference(neigh);
      n.addClass("hovered");
      neigh.connectedEdges().addClass("edge-hovered");
      rest.addClass("dimmed");
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("hovered edge-hovered dimmed");
    });

    // ---- edge hover: tooltip + edge thickness + endpoint ring ----
    cy.on("mouseover", "edge", (evt) => {
      const e = evt.target as EdgeSingular;
      const tip = ensureTooltip();
      tip.innerHTML = buildTooltipHtml(e);
      tip.style.display = "block";
      positionTooltip(evt);
      e.addClass("edge-hovered");
      e.source().addClass("endpoint-hi");
      e.target().addClass("endpoint-hi");
    });
    cy.on("mousemove", "edge", positionTooltip);
    cy.on("mouseout", "edge", () => {
      if (tooltipRef.current) tooltipRef.current.style.display = "none";
      cy.edges().removeClass("edge-hovered");
      cy.nodes().removeClass("endpoint-hi");
    });

    // ---- drag node: Y locked to strata band ----
    cy.on("drag", "node", (evt) => {
      const n = evt.target as NodeSingular;
      const pos = positionsRef.current.get(n.id());
      if (pos != null) n.position("y", pos.y);
    });

    // ---- tap routing: node single → callback; edge → callback; bg → clear ----
    cy.on("tap", "node", (evt) => {
      const id = (evt.target as NodeSingular).id();
      callbacksRef.current.onNodeClick?.(id);
    });
    cy.on("tap", "edge", (evt) => {
      const e = evt.target as EdgeSingular;
      const raw = e.data("raw") as GraphEdge | undefined;
      if (raw && callbacksRef.current.onEdgeClick) {
        callbacksRef.current.onEdgeClick(raw);
      }
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        callbacksRef.current.onBackgroundClick?.();
      }
    });

    // ---- dbltap node: navigate to that company's Subject if mapped ----
    cy.on("dbltap", "node", (evt) => {
      const id = (evt.target as NodeSingular).id();
      const sid = subjectMapRef.current?.get(id);
      if (sid && callbacksRef.current.onNodeDoubleClick) {
        callbacksRef.current.onNodeDoubleClick(sid);
      }
    });

    cy.on("zoom pan", syncRail);
    cy.fit(undefined, 80);
    syncRail();
  }, [payload, anchorId, showOrphans, showLabels]);

  // Re-project the rail on container resize too.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => syncRail());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={wrapRef} className="ig-cy-wrap">
      <div ref={railRef} className="ig-strata-rail" aria-hidden="true" />
      <div ref={containerRef} className="ig-cy" />
      <div className="ig-graph-legend" aria-hidden="true">
        <div className="group">
          <span className="item" style={{ color: "var(--teal)" }}>
            <span className="sw" /> supplies_to
          </span>
          <span className="item" style={{ color: "var(--warn)" }}>
            <span className="sw dashed" /> competes_with
          </span>
          <span className="item" style={{ color: "var(--role-buyer)" }}>
            <span className="sw" /> themed_under
          </span>
        </div>
        <div className="group">
          <span className="item">
            <span className="dot" style={{ background: "var(--role-anchor)" }} /> anchor
          </span>
          <span className="item">
            <span className="dot" style={{ background: "var(--role-buyer)" }} /> buyer
          </span>
          <span className="item">
            <span className="dot" style={{ background: "var(--role-supplier)" }} /> supplier
          </span>
          <span className="item">
            <span className="dot" style={{ background: "var(--role-competitor)" }} /> competitor
          </span>
        </div>
      </div>
    </div>
  );
}

function morphInto(
  cy: Core,
  cyNodes: Array<{ data: Record<string, unknown>; position?: { x: number; y: number } }>,
  cyEdges: Array<{ data: Record<string, unknown> }>,
  positions: Map<string, { x: number; y: number }>,
) {
  const newNodeData = new Map(
    cyNodes.map((d) => [String(d.data.id), d]),
  );
  const newEdgeData = new Map(cyEdges.map((d) => [String(d.data.id), d]));

  const stale = cy.elements().filter((el) =>
    el.isNode() ? !newNodeData.has(el.id()) : !newEdgeData.has(el.id()),
  );
  if (stale.length) {
    stale.animate(
      { style: { opacity: 0 } },
      { duration: FADE_DURATION, easing: "ease-out" },
    );
    setTimeout(() => stale.remove(), FADE_DURATION + 20);
  }

  cy.nodes().forEach((n) => {
    const nd = newNodeData.get(n.id());
    if (!nd) return;
    n.data("role", nd.data.role);
    n.data("color", nd.data.color);
    n.data("raw", nd.data.raw);
    if (nd.data.isAnchor) n.data("isAnchor", true);
    else n.removeData("isAnchor");
    const pos = positions.get(n.id());
    if (pos) {
      n.animate(
        { position: pos, style: { opacity: 1 } },
        { duration: MORPH_DURATION, easing: "ease-in-out" },
      );
    }
  });

  cy.edges().forEach((e) => {
    const ed = newEdgeData.get(e.id());
    if (!ed) return;
    e.data("normWidth", ed.data.normWidth);
    e.data("raw", ed.data.raw);
  });

  const existingNodeIds = new Set(cy.nodes().map((n) => n.id()));
  const existingEdgeIds = new Set(cy.edges().map((e) => e.id()));
  const toAdd = [
    ...cyNodes.filter((d) => !existingNodeIds.has(String(d.data.id))),
    ...cyEdges.filter((d) => !existingEdgeIds.has(String(d.data.id))),
  ];
  if (toAdd.length) {
    const added = cy.add(toAdd as cytoscape.ElementDefinition[]);
    added.style("opacity", 0);
    added.animate(
      { style: { opacity: 1 } },
      { duration: MORPH_DURATION, easing: "ease-in" },
    );
  }

  cy.animate(
    { fit: { eles: cy.elements(), padding: 60 } },
    { duration: MORPH_DURATION, easing: "ease-in-out" },
  );
}
