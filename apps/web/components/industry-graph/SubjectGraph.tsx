"use client";

import cytoscape from "cytoscape";
import type { Core, NodeSingular } from "cytoscape";
import { useEffect, useRef } from "react";
import {
  classifyRoles,
  colorForRole,
  computePositions,
  cssVar,
  type GraphPayload,
  strongestWeight,
} from "./cytoscape-helpers";

const MORPH_DURATION = 650;
const FADE_DURATION = 260;

type Props = {
  payload: GraphPayload | null;
  anchorId: string;
  showOrphans?: boolean;
  showLabels?: boolean;
  onNodeClick?: (id: string) => void;
};

export function SubjectGraph({
  payload,
  anchorId,
  showOrphans = false,
  showLabels = true,
  onNodeClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, []);

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

    const { positions } = computePositions(visibleNodes, roles, visibleEdges, anchorId);

    const maxW = Math.max(...visibleEdges.map(strongestWeight), 0.001);
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
      return { data, position: positions.get(n.id) };
    });
    const cyEdges = visibleEdges.map((e) => ({
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
        weight: strongestWeight(e),
        normWidth: 0.6 + 3.2 * (strongestWeight(e) / maxW),
        raw: e,
      },
    }));

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
          width: 96,
          height: 96,
          "border-width": 3.2,
          "border-color": cssVar("--role-anchor"),
          "font-family": "Fraunces, Songti SC, Georgia, serif",
          "font-size": 16,
          "font-weight": 500,
          "background-color": cssVar("--abyss"),
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
    ];

    // Morph path: when the cy instance already exists, update in place.
    if (cyRef.current) {
      morphInto(cyRef.current, cyNodes, cyEdges, positions);
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

    if (onNodeClick) {
      cyRef.current.on("tap", "node", (evt) => {
        const id = (evt.target as NodeSingular).id();
        onNodeClick(id);
      });
    }

    cyRef.current.fit(undefined, 60);
  }, [payload, anchorId, showOrphans, showLabels, onNodeClick]);

  return <div ref={containerRef} className="ig-cy" />;
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
