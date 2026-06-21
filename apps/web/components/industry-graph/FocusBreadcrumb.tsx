"use client";

import Link from "next/link";
import { useState } from "react";
import type { GraphPayload } from "./cytoscape-helpers";
import { type Locale } from "../../lib/i18n";

// Kind → demo's level label. Themes live above SubThemes which live above
// Technologies, Companies, Products, Components. Matches industry-graph-demo.html.
const KIND_LEVEL: Record<string, string> = {
  Theme: "L1",
  SubTheme: "L2",
  Technology: "L3",
  Company: "L4",
  Product: "L5",
  Component: "L6",
};

type SubjectListRow = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
};

type Segment = {
  id: string;
  label: string;
  kind: string;
  level: string;
  virtual?: boolean;
  current?: boolean;
  subjectId?: string;
  alt?: Segment[];
};

type Props = {
  subject: { type: "company" | "theme"; target_entity_id: string; display_name: string };
  graph: GraphPayload | null;
  allSubjects: SubjectListRow[];
  locale: Locale;
};

// Walk up from the current anchor using the relations carried in the
// projection: Company → SubTheme via `themed_under` (target). SubThemes
// without explicit parents fall under the synthetic L1 "AI" root, which
// matches the demo's convention.
function buildPath(props: Props): Segment[] {
  const { subject, graph, allSubjects } = props;
  const target = subject.target_entity_id;
  const subjectByTarget = new Map(
    allSubjects.map((s) => [s.target_entity_id, s.id]),
  );

  const current: Segment = {
    id: target,
    label: subject.display_name,
    kind: subject.type === "company" ? "Company" : "SubTheme",
    level: subject.type === "company" ? "L4" : "L2",
    current: true,
    subjectId: subjectByTarget.get(target),
  };

  const path: Segment[] = [current];

  if (graph) {
    // Up-edges from the anchor: `themed_under` targets (SubTheme).
    const upTargets = graph.edges
      .filter(
        (e) =>
          e.source === target &&
          (e.type === "themed_under" || e.type === "part_of"),
      )
      .map((e) => e.target);
    // Also surface subtheme ids declared as a facet on the anchor node.
    const anchorNode = graph.nodes.find((n) => n.id === target);
    const facetSubthemes = (anchorNode?.facets as Record<string, unknown> | undefined)
      ?.subtheme;
    if (Array.isArray(facetSubthemes)) {
      for (const st of facetSubthemes) {
        if (typeof st === "string" && !upTargets.includes(st)) upTargets.push(st);
      }
    }

    if (upTargets.length > 0) {
      const primaryId = upTargets[0];
      const primaryNode = graph.nodes.find((n) => n.id === primaryId);
      const primary: Segment = {
        id: primaryId,
        label: primaryNode?.label ?? primaryId,
        kind: primaryNode?.kind ?? "SubTheme",
        level: KIND_LEVEL[primaryNode?.kind ?? "SubTheme"] ?? "L2",
        subjectId: subjectByTarget.get(primaryId),
      };
      // Alternate parents — render as a +N chip the user can cycle through.
      primary.alt = upTargets.slice(1).map((id) => {
        const n = graph.nodes.find((x) => x.id === id);
        return {
          id,
          label: n?.label ?? id,
          kind: n?.kind ?? "SubTheme",
          level: KIND_LEVEL[n?.kind ?? "SubTheme"] ?? "L2",
          subjectId: subjectByTarget.get(id),
        };
      });
      path.unshift(primary);
    }
  }

  // Always cap with the synthetic L1 root, matching the demo.
  path.unshift({
    id: "L1_AI",
    label: "AI",
    kind: "Theme",
    level: "L1",
    virtual: true,
  });

  return path;
}

export function FocusBreadcrumb(props: Props) {
  const isZh = props.locale === "zh";
  const path = buildPath(props);
  const [altIndex, setAltIndex] = useState<Record<string, number>>({});

  // Sibling alternates of the CURRENT focus: all .alt of the primary parent.
  // We surface them in the row below as L2 SUBTHEME chips. Click-to-navigate
  // when the alt has a Subject.
  const currentIdx = path.findIndex((s) => s.current);
  const parent = currentIdx > 0 ? path[currentIdx - 1] : null;
  const parentAlts = parent?.alt ?? [];

  function renderSegment(seg: Segment, i: number) {
    const isCurrent = seg.current;
    const classes = ["bc-item"];
    if (isCurrent) classes.push("current");
    if (seg.virtual) classes.push("virtual");
    const content = (
      <>
        <span className="bc-item-kind">{seg.level}</span>
        <span>{seg.label}</span>
      </>
    );
    if (isCurrent || seg.virtual) {
      return (
        <span className={classes.join(" ")} key={`${seg.id}-${i}`}>
          {content}
        </span>
      );
    }
    if (seg.subjectId) {
      return (
        <Link
          href={`/industry-graph/${encodeURIComponent(seg.subjectId)}`}
          className={classes.join(" ")}
          key={`${seg.id}-${i}`}
          title={isZh ? `跳到 ${seg.label}` : `Open ${seg.label}`}
        >
          {content}
        </Link>
      );
    }
    return (
      <span className={classes.join(" ")} key={`${seg.id}-${i}`} title={seg.id}>
        {content}
      </span>
    );
  }

  return (
    <div className="ig-focus-bar">
      <div className="ig-focus-bc">
        <span className="ig-focus-eyebrow">{isZh ? "焦点" : "Focus"}</span>
        <div className="ig-focus-trail">
          {path.map((seg, i) => (
            <span className="ig-focus-trail-seg" key={`seg-${seg.id}-${i}`}>
              {i > 0 ? <span className="bc-sep">▸</span> : null}
              {renderSegment(seg, i)}
              {seg.alt && seg.alt.length > 0 ? (
                <button
                  type="button"
                  className="bc-chip"
                  title={
                    isZh
                      ? `其他父主题:\n• ${seg.alt.map((a) => a.label).join("\n• ")}\n点击循环切换`
                      : `Other parents:\n• ${seg.alt.map((a) => a.label).join("\n• ")}\nClick to cycle`
                  }
                  onClick={() => {
                    const ai = altIndex[seg.id] ?? 0;
                    const next = (ai + 1) % seg.alt!.length;
                    setAltIndex({ ...altIndex, [seg.id]: next });
                  }}
                >
                  +{seg.alt.length}
                </button>
              ) : null}
            </span>
          ))}
        </div>
      </div>

      {parentAlts.length > 0 ? (
        <div className="ig-focus-alts">
          <span className="ig-focus-alts-label">
            {parent?.level} {parent?.kind === "SubTheme" ? "SUBTHEME" : parent?.kind} · {isZh ? "并列父项" : "PARENT"}
          </span>
          <div className="ig-focus-alts-chips">
            {/* Render the primary parent + every alt as side-by-side chips,
                so the user can see they're sibling alternates. The primary
                stays styled "active". */}
            {parent ? (
              parent.subjectId ? (
                <Link
                  href={`/industry-graph/${encodeURIComponent(parent.subjectId)}`}
                  className="ig-focus-alt-chip active"
                  key={`alt-primary-${parent.id}`}
                >
                  <span className="bc-item-kind">{parent.level}</span>
                  {parent.label}
                </Link>
              ) : (
                <span
                  className="ig-focus-alt-chip active"
                  key={`alt-primary-${parent.id}`}
                >
                  <span className="bc-item-kind">{parent.level}</span>
                  {parent.label}
                </span>
              )
            ) : null}
            {parentAlts.map((a) =>
              a.subjectId ? (
                <Link
                  href={`/industry-graph/${encodeURIComponent(a.subjectId)}`}
                  className="ig-focus-alt-chip"
                  key={`alt-${a.id}`}
                >
                  <span className="bc-item-kind">{a.level}</span>
                  {a.label}
                </Link>
              ) : (
                <span className="ig-focus-alt-chip" key={`alt-${a.id}`}>
                  <span className="bc-item-kind">{a.level}</span>
                  {a.label}
                </span>
              ),
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
