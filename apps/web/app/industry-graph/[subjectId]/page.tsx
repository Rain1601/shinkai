"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { PortalShell } from "../../../components/portal/PortalShell";
import { ActivityFeed } from "../../../components/industry-graph/ActivityFeed";
import { EdgePane } from "../../../components/industry-graph/EdgePane";
import { SubjectGraph } from "../../../components/industry-graph/SubjectGraph";
import { ThemeMembersGrid } from "../../../components/industry-graph/ThemeMembersGrid";
import type {
  GraphEdge,
  GraphPayload,
} from "../../../components/industry-graph/cytoscape-helpers";
import { type Locale } from "../../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type SubjectVersionChangeSummary = {
  entities_added: number;
  entities_updated: number;
  entities_deprecated: number;
  relations_added: number;
  relations_updated: number;
  relations_deprecated: number;
  highlights: string[];
};

type SubjectVersion = {
  id: string;
  subject_id: string;
  version_no: number;
  run_id: string;
  snapshot_from: number;
  snapshot_to: number;
  triggered_by: "manual" | "schedule" | "agent" | "migration";
  status: "pending" | "running" | "completed" | "failed";
  started_at: string;
  ended_at: string | null;
  scope_node_ids: string[];
  rationale: string;
  change_summary: SubjectVersionChangeSummary | null;
  task_prompt?: string;
  error?: string | null;
};

type SubjectDetail = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
  schedule: { cron: string | null; autonomous: boolean };
  versions: SubjectVersion[];
};

type SubjectListRow = {
  id: string;
  type: "company" | "theme";
  display_name: string;
  target_entity_id: string;
};

function formatRelative(iso: string | null, locale: Locale): string {
  if (!iso) return locale === "zh" ? "尚未运行" : "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = (Date.now() - t) / 1000;
  const abs = Math.abs(delta);
  const units: [number, string, string][] = [
    [86400, "天", "d"],
    [3600, "小时", "h"],
    [60, "分钟", "m"],
    [1, "秒", "s"],
  ];
  for (const [s, zh, en] of units) {
    if (abs >= s) {
      const n = Math.floor(abs / s);
      return locale === "zh" ? `${n}${zh}前` : `${n}${en} ago`;
    }
  }
  return locale === "zh" ? "刚刚" : "just now";
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export default function IndustryGraphSubjectDetail({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}) {
  const { subjectId: rawId } = use(params);
  const subjectId = decodeURIComponent(rawId);
  const searchParams = useSearchParams();
  const focusEventId = searchParams.get("event");

  // When arriving with ?event=<id>, scroll the matching row into view
  // once the feed has loaded. The ActivityFeed renders a <li> keyed on
  // event_id-subject_id, so a querySelectorAll is enough — no ref dance.
  useEffect(() => {
    if (!focusEventId) return;
    const handle = setTimeout(() => {
      const el = document.querySelector(
        `.ig-detail-activity .ig-activity [href*="event=${focusEventId}"]`,
      );
      if (el instanceof HTMLElement) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.closest(".ig-activity")?.classList.add("focused");
      }
    }, 600);
    return () => clearTimeout(handle);
  }, [focusEventId, subjectId]);

  const [subject, setSubject] = useState<SubjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [allSubjects, setAllSubjects] = useState<SubjectListRow[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const isZh = locale === "zh";

  function changeLocale(next: Locale) {
    setLocale(next);
    try {
      window.localStorage.setItem("shinkai.locale", next);
    } catch {}
  }

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("shinkai.locale");
      if (stored === "zh" || stored === "en") setLocale(stored);
    } catch {}
  }, []);

  const fetchSubject = useCallback(async () => {
    try {
      const r = await fetch(
        `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}`,
        { cache: "no-store" },
      );
      if (!r.ok) throw new Error(`subject ${r.status}`);
      const d: SubjectDetail = await r.json();
      setSubject(d);
      setError(null);
      if (selectedVersion === null && d.versions.length > 0) {
        setSelectedVersion(d.versions[d.versions.length - 1].version_no);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [subjectId, selectedVersion]);

  useEffect(() => {
    void fetchSubject();
  }, [fetchSubject]);

  // Pull the full Subject catalog once — used by the AnchorPane to render
  // "参与主题" chips that link to the matching Theme subjects.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch(`${API_URL}/api/v1/industry_graph/subjects`, {
          cache: "no-store",
        });
        if (!r.ok) return;
        const d: { subjects: SubjectListRow[] } = await r.json();
        if (!cancelled) setAllSubjects(d.subjects);
      } catch {
        // best effort — missing catalog just suppresses the chips
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!subject || selectedVersion === null) return;
    // Switching versions invalidates any selected edge — the new snapshot
    // may not even contain the same edge id.
    setSelectedEdge(null);
    // Theme subjects don't have a meaningful anchor BFS — Stage 3 renders
    // ThemeMembersGrid instead, no cytoscape — so skip the fetch entirely.
    if (subject.type === "theme") {
      setGraph(null);
      setGraphLoading(false);
      return;
    }
    let cancelled = false;
    setGraphLoading(true);
    async function load() {
      try {
        const r = await fetch(
          `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(
            subjectId,
          )}/versions/${selectedVersion}/graph?depth=1`,
          { cache: "no-store" },
        );
        if (!r.ok) throw new Error(`graph ${r.status}`);
        const d: GraphPayload = await r.json();
        if (cancelled) return;
        setGraph(d);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [subject, selectedVersion, subjectId]);

  // Poll while a run is in flight so the timeline updates without manual refresh.
  useEffect(() => {
    if (!subject) return;
    const pending = subject.versions.find(
      (v) => v.status === "running" || v.status === "pending",
    );
    if (!pending) return;
    const handle = setInterval(() => {
      void fetchSubject();
    }, 4000);
    return () => clearInterval(handle);
  }, [subject, fetchSubject]);

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    try {
      const r = await fetch(
        `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ triggered_by: "manual" }),
        },
      );
      if (r.status === 409) {
        setRunError(isZh ? "已有分析在跑,请稍后" : "Another run is in flight; try later");
      } else if (r.status === 503) {
        const d = await r.json().catch(() => ({ detail: "503" }));
        setRunError(`${d.detail || "503"}`);
      } else if (!r.ok) {
        setRunError(`HTTP ${r.status}`);
      } else {
        await fetchSubject();
      }
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const activeVersion =
    subject && selectedVersion !== null
      ? subject.versions.find((v) => v.version_no === selectedVersion) ?? null
      : null;

  return (
    <PortalShell
      active="industry"
      locale={locale}
      onLocaleChange={changeLocale}
      title={subject?.display_name ?? (isZh ? "加载中…" : "Loading…")}
      subtitle={
        subject
          ? isZh
            ? `${subject.type === "company" ? "公司" : "主题"} · ${subject.target_entity_id}`
            : `${subject.type} · ${subject.target_entity_id}`
          : undefined
      }
      actions={
        <Link href="/industry-graph" className="live-pill">
          {isZh ? "← 返回列表" : "← back to list"}
        </Link>
      }
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="ig-detail-workspace">
        {/* LEFT — vertical version timeline */}
        <aside className="ig-detail-timeline">
          <div className="live-themes-header">
            <span className="label">{isZh ? "版本历史" : "History"}</span>
            <span className="muted">
              {subject ? `v${subject.versions.length}` : ""}
            </span>
          </div>

          {loading ? (
            <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>
          ) : !subject ? (
            <p className="muted live-empty">{isZh ? "未找到 subject" : "subject not found"}</p>
          ) : (
            <>
              <ul className="ig-timeline">
                {[...subject.versions].reverse().map((v) => {
                  const isActive = v.version_no === selectedVersion;
                  return (
                    <li
                      key={v.id}
                      className={`ig-timeline-row ${isActive ? "active" : ""} status-${v.status}`}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedVersion(v.version_no)}
                        className="ig-timeline-button"
                      >
                        <span className="ig-timeline-dot" />
                        <span className="ig-timeline-meta">
                          <span className="ig-timeline-ver">v{v.version_no}</span>
                          <span className="ig-timeline-when">
                            {shortDate(v.ended_at ?? v.started_at)}
                          </span>
                        </span>
                        <span className="ig-timeline-rationale">
                          {v.rationale || v.task_prompt?.slice(0, 60) || v.triggered_by}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="ig-timeline-actions">
                <button
                  type="button"
                  onClick={handleRun}
                  disabled={running}
                  className="ig-run-btn"
                >
                  {running ? (isZh ? "提交中…" : "Starting…") : isZh ? "+ 新分析" : "+ Run new"}
                </button>
                {runError ? <p className="muted error-copy">{runError}</p> : null}
              </div>
            </>
          )}
        </aside>

        {/* MIDDLE — graph + version details */}
        <section className="ig-detail-main">
          <div className="ig-graph-area">
            {subject?.type === "theme" ? (
              // Theme subjects don't BFS-anchor cleanly (SubTheme edges are
              // semantically different from supply_to / competes_with). Render
              // the member companies grid instead — Stage 3 of the merge plan.
              <ThemeMembersGrid subjectId={subjectId} locale={locale} />
            ) : graphLoading ? (
              <p className="muted live-empty">{isZh ? "渲染中…" : "Rendering…"}</p>
            ) : !graph || graph.nodes.length === 0 ? (
              <p className="muted live-empty">
                {isZh
                  ? "这个版本对应的锚点在图中暂未找到。"
                  : "Anchor not present at this version's snapshot."}
              </p>
            ) : (
              <SubjectGraph
                payload={graph}
                anchorId={subject?.target_entity_id ?? ""}
                showOrphans={false}
                showLabels={true}
                onEdgeClick={(edge) => setSelectedEdge(edge)}
                onBackgroundClick={() => setSelectedEdge(null)}
                onNodeClick={() => setSelectedEdge(null)}
              />
            )}
          </div>

          <div className="ig-version-card">
            {activeVersion ? (
              <>
                <div className="ig-version-header">
                  <span className="ig-version-eyebrow">
                    {isZh ? `v${activeVersion.version_no} · 详情` : `v${activeVersion.version_no} · details`}
                  </span>
                  <span className={`ig-version-status status-${activeVersion.status}`}>
                    {activeVersion.status}
                  </span>
                </div>
                <dl className="ig-version-dl">
                  <dt>{isZh ? "触发方" : "trigger"}</dt>
                  <dd>{activeVersion.triggered_by}</dd>
                  <dt>{isZh ? "Agent" : "agent"}</dt>
                  <dd>
                    {activeVersion.run_id}
                    {activeVersion.task_prompt
                      ? ` · ${activeVersion.task_prompt.length}ch prompt`
                      : ""}
                  </dd>
                  <dt>{isZh ? "Snapshot" : "snapshot"}</dt>
                  <dd>
                    v{activeVersion.snapshot_from} → v{activeVersion.snapshot_to}
                  </dd>
                  <dt>{isZh ? "时间" : "ended"}</dt>
                  <dd>
                    {formatRelative(
                      activeVersion.ended_at ?? activeVersion.started_at,
                      locale,
                    )}
                  </dd>
                  {activeVersion.change_summary ? (
                    <>
                      <dt>{isZh ? "变更" : "changes"}</dt>
                      <dd>
                        +{activeVersion.change_summary.entities_added} ent · +
                        {activeVersion.change_summary.relations_added} rel
                      </dd>
                    </>
                  ) : null}
                  {activeVersion.error ? (
                    <>
                      <dt>{isZh ? "错误" : "error"}</dt>
                      <dd className="error-copy">{activeVersion.error}</dd>
                    </>
                  ) : null}
                </dl>
                {activeVersion.change_summary?.highlights?.length ? (
                  <ul className="ig-version-highlights">
                    {activeVersion.change_summary.highlights.slice(0, 6).map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    {isZh ? "本版本没有变更摘要。" : "No changes recorded for this version."}
                  </p>
                )}
              </>
            ) : (
              <p className="muted">{isZh ? "选一个版本查看详情" : "Pick a version"}</p>
            )}
          </div>

          {/* Historical Run events that touched this Subject. Replaces /live's
              right-rail Analyses list. Only renders when there's something
              to show — empty state lives inside ActivityFeed. */}
          <div className="ig-detail-activity">
            <header className="ig-detail-activity-head">
              <span className="ig-detail-activity-eyebrow">
                {isZh ? "历史分析活动" : "Past analytical activity"}
              </span>
            </header>
            <ActivityFeed subjectId={subjectId} locale={locale} limit={30} />
          </div>
        </section>

        {/* RIGHT — Anchor card or Edge inspection, whichever the user has
            focused. Click an edge in the graph to swap. */}
        {selectedEdge && graph ? (
          <EdgePane
            edge={selectedEdge}
            graph={graph}
            subjectMap={
              new Map(
                allSubjects
                  .filter((s) => s.type === "company")
                  .map((s) => [s.target_entity_id, s.id]),
              )
            }
            locale={locale}
            onClear={() => setSelectedEdge(null)}
          />
        ) : (
          <AnchorPane
            subject={subject}
            graph={graph}
            allSubjects={allSubjects}
            locale={locale}
          />
        )}
      </div>
    </PortalShell>
  );
}

type AnchorPaneProps = {
  subject: SubjectDetail | null;
  graph: GraphPayload | null;
  allSubjects: SubjectListRow[];
  locale: Locale;
};

function AnchorPane({ subject, graph, allSubjects, locale }: AnchorPaneProps) {
  const isZh = locale === "zh";
  if (!subject) {
    return (
      <aside className="ig-anchor-pane">
        <p className="muted live-empty">{isZh ? "加载中…" : "Loading…"}</p>
      </aside>
    );
  }
  // Theme subjects never fetch a graph (see effect guard) — render the
  // header card and skip the relations tables. Members live in the middle.
  const anchorId = subject.target_entity_id;
  const anchorNode = graph?.nodes.find((n) => n.id === anchorId) ?? null;

  type EdgeWithOther = {
    edge: GraphPayload["edges"][number];
    other: GraphPayload["nodes"][number] | null;
  };
  const downstream: EdgeWithOther[] = [];
  const upstream: EdgeWithOther[] = [];
  const competes: EdgeWithOther[] = [];

  function nodeOf(id: string): GraphPayload["nodes"][number] | null {
    return graph?.nodes.find((n) => n.id === id) ?? null;
  }

  for (const e of graph?.edges ?? []) {
    if (e.type === "supplies_to") {
      if (e.source === anchorId) downstream.push({ edge: e, other: nodeOf(e.target) });
      else if (e.target === anchorId) upstream.push({ edge: e, other: nodeOf(e.source) });
    } else if (e.type === "competes_with") {
      const otherId = e.source === anchorId ? e.target : e.target === anchorId ? e.source : null;
      if (otherId) competes.push({ edge: e, other: nodeOf(otherId) });
    }
  }
  // Sort by latest year share descending so the most material relations rise.
  function latestShare(e: GraphPayload["edges"][number]): number {
    const years = Object.keys(e.wbp).sort();
    if (!years.length) return 0;
    const v = e.wbp[years[years.length - 1]];
    return v?.[0] ?? 0;
  }
  downstream.sort((a, b) => latestShare(b.edge) - latestShare(a.edge));
  upstream.sort((a, b) => latestShare(b.edge) - latestShare(a.edge));

  function renderList(arr: EdgeWithOther[], arrow: string, side: "to" | "from") {
    if (!arr.length) return null;
    return (
      <ul className="ig-rel-list">
        {arr.slice(0, 10).map(({ edge, other }) => {
          const label = other?.label ?? (side === "to" ? edge.target : edge.source);
          const years = Object.keys(edge.wbp ?? {}).sort();
          const latest = years[years.length - 1];
          const cells = years.slice(-3).map((y) => {
            const vals = edge.wbp[y] ?? [];
            const share = typeof vals[0] === "number" ? Math.round(vals[0] * 100) : null;
            return (
              <span className="ig-rel-cell" key={y}>
                <span className="ig-rel-y">{y}</span>
                <span className="ig-rel-v">{share != null ? `${share}%` : "—"}</span>
              </span>
            );
          });
          const evid = edge.evidence_type === "soft_inference" ? "soft" : "hard";
          return (
            <li key={edge.id} className="ig-rel">
              <div className="ig-rel-head">
                <span className="ig-rel-arrow">{arrow}</span>
                <span className="ig-rel-name">{label}</span>
                <span className={`ig-rel-evid ${evid}`}>{evid}</span>
              </div>
              {latest ? <div className="ig-rel-weights">{cells}</div> : null}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <aside className="ig-anchor-pane">
      <span className="ig-anchor-eyebrow">
        {subject.type === "company" ? (isZh ? "公司" : "Company") : isZh ? "主题" : "Theme"}
      </span>
      <h2 className="ig-anchor-name">
        <span className="ig-anchor-bar" />
        {subject.display_name}
      </h2>
      {anchorNode?.aliases?.length ? (
        <p className="ig-anchor-aliases">{anchorNode.aliases.join(" · ")}</p>
      ) : null}
      {anchorNode?.desc ? <p className="ig-anchor-desc">{anchorNode.desc}</p> : null}

      <dl className="ig-anchor-dl">
        <dt>id</dt>
        <dd>{anchorId}</dd>
        {anchorNode?.layer ? (
          <>
            <dt>{isZh ? "层位" : "stratum"}</dt>
            <dd>{anchorNode.layer}</dd>
          </>
        ) : null}
        {anchorNode?.confidence != null ? (
          <>
            <dt>{isZh ? "置信" : "confidence"}</dt>
            <dd>{Math.round((anchorNode.confidence ?? 0) * 100)}%</dd>
          </>
        ) : null}
        {anchorNode?.source ? (
          <>
            <dt>{isZh ? "来源" : "source"}</dt>
            <dd>{anchorNode.source}</dd>
          </>
        ) : null}
      </dl>

      {/* Cross-link to Theme subjects this Company is filed under.
          Pulled from anchorNode.facets.subtheme; chips link to the
          matching Theme subject. Only rendered for type=company since
          themes themselves render their members list instead. */}
      {subject.type === "company" ? (() => {
        const subFacet = (anchorNode?.facets as Record<string, unknown> | undefined)?.[
          "subtheme"
        ];
        const targets = Array.isArray(subFacet)
          ? subFacet.filter((v): v is string => typeof v === "string")
          : typeof subFacet === "string"
            ? [subFacet]
            : [];
        if (!targets.length) return null;
        const themeByTarget = new Map(
          allSubjects.filter((s) => s.type === "theme").map((s) => [s.target_entity_id, s]),
        );
        const chips = targets
          .map((t) => themeByTarget.get(t))
          .filter((s): s is SubjectListRow => Boolean(s));
        if (!chips.length) return null;
        return (
          <div className="ig-anchor-themes">
            <span className="ig-anchor-themes-label">
              {isZh ? "参与主题" : "Member of"}
            </span>
            <span className="ig-anchor-themes-chips">
              {chips.map((s) => (
                <Link
                  key={s.id}
                  href={`/industry-graph/${encodeURIComponent(s.id)}`}
                  className="ig-theme-chip"
                >
                  {s.display_name}
                </Link>
              ))}
            </span>
          </div>
        );
      })() : null}

      {/* Downstream / Upstream / Competes only meaningful for Company subjects.
          Theme subjects show their member companies in the middle area
          instead — listing them here too would just duplicate the surface. */}
      {subject.type === "company" ? (
        <>
          {downstream.length > 0 ? (
            <>
              <div className="ig-rel-head-row">
                <span className="ig-rel-head-arrow">↓</span>
                <h3>{isZh ? "下游 · 客户" : "Downstream"}</h3>
                <span className="ig-rel-count">{downstream.length}</span>
              </div>
              {renderList(downstream, "→", "to")}
            </>
          ) : null}

          {upstream.length > 0 ? (
            <>
              <div className="ig-rel-head-row">
                <span className="ig-rel-head-arrow">↑</span>
                <h3>{isZh ? "上游 · 供应商" : "Upstream"}</h3>
                <span className="ig-rel-count">{upstream.length}</span>
              </div>
              {renderList(upstream, "←", "from")}
            </>
          ) : null}

          {competes.length > 0 ? (
            <>
              <div className="ig-rel-head-row">
                <span className="ig-rel-head-arrow">↔</span>
                <h3>{isZh ? "竞争对手" : "Competes"}</h3>
                <span className="ig-rel-count">{competes.length}</span>
              </div>
              {renderList(competes, "↔", "to")}
            </>
          ) : null}
        </>
      ) : null}
    </aside>
  );
}
