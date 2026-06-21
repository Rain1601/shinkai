/**
 * Pure helpers ported from apps/web/public/industry-graph-live.html so the
 * Detail page (which renders a graph at a chosen SubjectVersion) can reuse
 * the same anchor-focused strata layout + role colouring + weight scaling
 * without resurrecting the static file.
 *
 * No DOM access; the React wrapper component does the mounting and styling.
 */

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: {
    node_count: number;
    edge_count: number;
    anchor?: string;
    snapshot_version?: number;
    subject_version?: number;
    [k: string]: unknown;
  };
};

export type GraphNode = {
  id: string;
  label: string;
  kind: string;
  layer: string | null;
  desc: string;
  aliases: string[];
  confidence: number | null;
  source: string;
  facets: Record<string, unknown>;
  attributes: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  wbp: Record<string, number[]>;
  confidence: number | null;
  evidence_type: string | null;
  evidence_ref: string;
};

export type Role =
  | "anchor"
  | "buyer"
  | "supplier"
  | "competitor"
  | "related"
  | "other";

// Top of list = closest to anchor; bottom = deepest upstream. Mirrors
// industry_graph/layer_map.LAYER_ORDER for the supplier band.
export const SUPPLIER_LAYER_ORDER = [
  "ai_model",
  "assembly",
  "designer",
  "advanced_packaging",
  "memory",
  "testing",
  "foundry",
  "optical",
  "robotics",
  "battery",
  "power",
  "cooling",
  "infrastructure",
  "passive",
  "materials",
] as const;

export const LAYER_LABEL: Record<string, string> = {
  ai_model: "AI Model",
  designer: "Designer",
  assembly: "Assembly",
  advanced_packaging: "Packaging",
  memory: "Memory",
  testing: "Test / OSAT",
  foundry: "Foundry",
  optical: "Optical",
  robotics: "Robotics",
  battery: "Battery",
  power: "Power",
  cooling: "Cooling",
  infrastructure: "Infra",
  passive: "Passives",
  materials: "Materials",
  theme: "Theme",
  other: "Other",
};

export const ROLE_VAR: Record<Role, string> = {
  anchor: "--role-anchor",
  buyer: "--role-buyer",
  supplier: "--role-supplier",
  competitor: "--role-competitor",
  related: "--role-other",
  other: "--role-other",
};

const W_VIRT = 1400;
const H_VIRT = 1100;

export function classifyRoles(
  payload: GraphPayload,
  anchorId: string,
): Map<string, Role> {
  const roles = new Map<string, Role>();
  roles.set(anchorId, "anchor");
  for (const e of payload.edges) {
    if (e.type === "supplies_to") {
      if (e.source === anchorId && !roles.has(e.target)) roles.set(e.target, "buyer");
      if (e.target === anchorId && !roles.has(e.source)) roles.set(e.source, "supplier");
    } else if (e.type === "competes_with") {
      const o = e.source === anchorId ? e.target : e.target === anchorId ? e.source : null;
      if (o && !roles.has(o)) roles.set(o, "competitor");
    }
  }
  for (const n of payload.nodes) {
    if (!roles.has(n.id)) {
      roles.set(n.id, n.kind === "Company" ? "related" : "other");
    }
  }
  return roles;
}

export function strongestWeight(edge: GraphEdge): number {
  let best = 0;
  for (const k of Object.keys(edge.wbp ?? {})) {
    const w = edge.wbp[k]?.[0];
    if (typeof w === "number" && w > best) best = w;
  }
  return best;
}

export type ComputedPositions = {
  positions: Map<string, { x: number; y: number }>;
  supplierLayers: string[];
  layerYByName: Map<string, number>;
};

export function computePositions(
  visibleNodes: GraphNode[],
  roles: Map<string, Role>,
  visibleEdges: GraphEdge[],
  anchorId: string,
): ComputedPositions {
  const strength = new Map<string, number>();
  for (const e of visibleEdges) {
    const w = strongestWeight(e);
    strength.set(e.source, Math.max(strength.get(e.source) ?? 0, w));
    strength.set(e.target, Math.max(strength.get(e.target) ?? 0, w));
  }

  const groups: Record<string, GraphNode[]> = {
    buyer: [],
    supplier: [],
    competitor: [],
    related: [],
    other: [],
  };
  for (const n of visibleNodes) {
    const role = roles.get(n.id);
    if (role === "anchor" || !role) continue;
    (groups[role] ?? groups.other).push(n);
  }
  for (const arr of Object.values(groups)) {
    arr.sort((a, b) => (strength.get(b.id) ?? 0) - (strength.get(a.id) ?? 0));
  }

  const positions = new Map<string, { x: number; y: number }>();
  positions.set(anchorId, { x: W_VIRT / 2, y: H_VIRT * 0.4 });

  function spreadRow(
    arr: GraphNode[],
    y: number,
    leftFrac: number,
    rightFrac: number,
    perRow = 9,
  ) {
    const n = arr.length;
    if (!n) return;
    const leftPad = W_VIRT * leftFrac;
    const rightPad = W_VIRT * rightFrac;
    const span = rightPad - leftPad;
    arr.forEach((node, i) => {
      const row = Math.floor(i / perRow);
      const inRow = i - row * perRow;
      const cnt = Math.min(perRow, n - row * perRow);
      const t = cnt === 1 ? 0.5 : inRow / (cnt - 1);
      const x = leftPad + t * span;
      const dir = y < H_VIRT * 0.4 ? -1 : y > H_VIRT * 0.4 ? +1 : 0;
      positions.set(node.id, { x, y: y + dir * row * 84 });
    });
  }

  spreadRow(groups.buyer, H_VIRT * 0.14, 0.08, 0.92, 8);

  const supplierByLayer = new Map<string, GraphNode[]>();
  for (const n of groups.supplier) {
    const layer = n.layer || "other";
    if (!supplierByLayer.has(layer)) supplierByLayer.set(layer, []);
    supplierByLayer.get(layer)!.push(n);
  }
  const supplierLayers: string[] = [];
  for (const l of SUPPLIER_LAYER_ORDER) if (supplierByLayer.has(l)) supplierLayers.push(l);
  for (const l of supplierByLayer.keys()) {
    if (!(SUPPLIER_LAYER_ORDER as readonly string[]).includes(l) && l !== "other") {
      supplierLayers.push(l);
    }
  }
  if (supplierByLayer.has("other")) supplierLayers.push("other");

  const layerYByName = new Map<string, number>();
  supplierLayers.forEach((layer, idx) => {
    const y = H_VIRT * 0.56 + idx * 95;
    layerYByName.set(layer, y);
    const arr = supplierByLayer.get(layer) ?? [];
    arr.sort((a, b) => (strength.get(b.id) ?? 0) - (strength.get(a.id) ?? 0));
    spreadRow(arr, y, 0.12, 0.88, 9);
  });

  groups.competitor.forEach((node, i) => {
    const col = Math.floor(i / 4);
    const row = i % 4;
    positions.set(node.id, { x: W_VIRT * 0.84 + col * 80, y: H_VIRT * 0.32 + row * 70 });
  });

  const sides = [...groups.related, ...groups.other];
  sides.forEach((node, i) => {
    const col = Math.floor(i / 5);
    const row = i % 5;
    positions.set(node.id, { x: W_VIRT * 0.08 - col * 80, y: H_VIRT * 0.3 + row * 60 });
  });

  return { positions, supplierLayers, layerYByName };
}

export function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function colorForRole(role: Role): string {
  return cssVar(ROLE_VAR[role]);
}
