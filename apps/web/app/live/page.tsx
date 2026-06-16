"use client";

import { useEffect, useMemo, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import { type Locale } from "../../lib/i18n";

type ThemeSummary = {
  theme_id: string;
  title: string;
  run_count: number;
  active_hypothesis_count: number;
  falsified_hypothesis_count: number;
  last_activity_ts: number;
  latest_run_id: string | null;
  running_count: number;
  cluster_id: string | null;
  cluster_name: string | null;
};

type ThemeGraph = {
  generated_at: number;
  generator: string;
  clusters: Array<{ cluster_id: string; cluster_name: string; rationale: string; theme_ids: string[] }>;
  edges: Array<{ from_theme_id: string; to_theme_id: string; kind: string; weight: number; reason: string }>;
  unclustered_theme_ids: string[];
  reject_reason: string | null;
};

type Session = {
  auth_required: boolean;
  role: string;
  capabilities: string[];
};

type ThemeEventSource = {
  url: string;
  title: string;
  publisher: string;
  tier: "primary" | "secondary" | "tertiary" | "agent_summary";
  reliability: number;
};

type ThemeEvent = {
  event_id: string;
  theme_id: string;
  category:
    | "earnings"
    | "m_and_a"
    | "product"
    | "regulation"
    | "supply_shock"
    | "industry"
    | "macro"
    | "other";
  event_ts: number;
  title: string;
  summary: string;
  key_facts: string[];
  tickers: string[];
  source: ThemeEventSource;
  relevance: number;
  ingested_at: number;
  metadata: Record<string, unknown>;
};

type ThemeIngestionSummary = {
  theme_id: string;
  started_at: number;
  finished_at: number;
  fetched_raw: number;
  structured: number;
  new_events: number;
  skipped_low_relevance: number;
  generator: string;
  reject_reason: string | null;
};

type ThemeEventsResponse = {
  events: ThemeEvent[];
  summary: ThemeIngestionSummary | null;
};

const UNCLUSTERED_KEY = "__unclustered__";

const CATEGORY_LABEL_ZH: Record<ThemeEvent["category"], string> = {
  earnings: "财报",
  m_and_a: "并购",
  product: "产品",
  regulation: "监管",
  supply_shock: "供应链",
  industry: "行业",
  macro: "宏观",
  other: "其他",
};

const CATEGORY_LABEL_EN: Record<ThemeEvent["category"], string> = {
  earnings: "Earnings",
  m_and_a: "M&A",
  product: "Product",
  regulation: "Regulation",
  supply_shock: "Supply",
  industry: "Industry",
  macro: "Macro",
  other: "Other",
};

function categoryLabel(category: ThemeEvent["category"], isZh: boolean) {
  return (isZh ? CATEGORY_LABEL_ZH : CATEGORY_LABEL_EN)[category] ?? category;
}

type ThemeRunSummary = {
  run_id: string;
  status: string;
  lifecycle_stage: string;
  anchor: string;
  last_activity_ts: number;
};

type ThemeDetail = {
  theme_id: string;
  title: string;
  runs: ThemeRunSummary[];
};

type AgentEvent = {
  event_id: string;
  type: string;
  ts: number | null;
  data: Record<string, unknown>;
};

type Run = {
  id: string;
  anchor: string;
  status: string;
  lifecycle_stage: string;
  events: AgentEvent[];
};

type EnrichedEvent = AgentEvent & { run_id: string; run_status: string };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

// Theme history milestones — the events that tell the theme's story.
// Excludes low-level chatter (tool_call, tool_result, role_step_*, usage,
// graph_delta, evidence_found firehose, planner_proposals, plan).
const MILESTONE_TYPES = new Set([
  "run_start",
  "run_recovered",
  "frontier_selected",
  "frontier_expanded",
  "frontier_reprioritized",
  "hypothesis_created",
  "hypothesis_confidence_updated",
  "candidate_scored",
  "judgment_created",
  "company_dossier_created",
  "company_deep_analysis_completed",
  "critic_persona_critique",
  "critic_aggregated",
  "checkpoint_raised",
  "checkpoint_released",
  "checklist_patch_proposed",
  "filter_policy_patch_proposed",
  "eval_completed",
  "done",
]);

// Analysis record types — concrete write-ups produced by the agent.
const ANALYSIS_TYPES = new Set([
  "company_dossier_created",
  "company_deep_analysis_completed",
  "judgment_created",
]);

function str(v: unknown): string {
  if (v === undefined || v === null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

function eventTitle(ev: AgentEvent, isZh: boolean): string {
  const t = ev.type;
  const d = ev.data ?? {};
  const layer = str(d.layer);
  const ticker = str(d.ticker) || str(d.symbol);
  const name = str(d.name);

  if (t === "run_start") return isZh ? `Run 启动 · ${str(d.anchor) || "—"}` : `Run start · ${str(d.anchor) || "—"}`;
  if (t === "run_recovered") return isZh ? "Run 恢复" : "Run recovered";
  if (t === "frontier_selected") return isZh ? `进入 ${layer || "新层"}` : `Enter ${layer || "layer"}`;
  if (t === "frontier_expanded") {
    const added = d.added ?? "?";
    return isZh ? `${layer} 扩展 +${added}` : `${layer} expand +${added}`;
  }
  if (t === "frontier_reprioritized") return isZh ? "Frontier 重排" : "Frontier reprioritized";
  if (t === "hypothesis_created") return isZh ? `假设 · ${layer}` : `Hypothesis · ${layer}`;
  if (t === "hypothesis_confidence_updated") {
    const conf = d.confidence !== undefined ? Number(d.confidence).toFixed(2) : "?";
    return isZh ? `${layer} 置信度 → ${conf}` : `${layer} confidence → ${conf}`;
  }
  if (t === "candidate_scored") {
    const score = d.combined_score !== undefined ? Number(d.combined_score).toFixed(2) : "?";
    return isZh ? `候选打分 · ${ticker} · ${score}` : `Candidate scored · ${ticker} · ${score}`;
  }
  if (t === "judgment_created") return isZh ? `判断 · ${layer}` : `Judgment · ${layer}`;
  if (t === "company_dossier_created") {
    const decision = str(d.decision);
    return isZh ? `档案 · ${ticker || name} · ${decision}` : `Dossier · ${ticker || name} · ${decision}`;
  }
  if (t === "company_deep_analysis_completed") {
    const decision = str(d.decision);
    return isZh ? `深析完成 · ${name || ticker} · ${decision}` : `Deep analysis · ${name || ticker} · ${decision}`;
  }
  if (t === "critic_persona_critique") {
    const persona = str(d.persona);
    return isZh ? `批评者 · ${persona}` : `Critic · ${persona}`;
  }
  if (t === "critic_aggregated") {
    const verdict = str(d.aggregated_verdict);
    return isZh ? `评审聚合 · ${verdict}` : `Critics aggregated · ${verdict}`;
  }
  if (t === "checkpoint_raised") return isZh ? `检查点 · ${str(d.reason)}` : `Checkpoint · ${str(d.reason)}`;
  if (t === "checkpoint_released") return isZh ? `检查点解除` : `Checkpoint released`;
  if (t === "checklist_patch_proposed") return isZh ? "提议 checklist 补丁" : "Checklist patch proposed";
  if (t === "filter_policy_patch_proposed") return isZh ? "提议过滤策略补丁" : "Filter policy patch proposed";
  if (t === "eval_completed") {
    const score = d.overall_score !== undefined ? Number(d.overall_score).toFixed(2) : "?";
    return isZh ? `评测完成 · ${score}` : `Eval done · ${score}`;
  }
  if (t === "done") return isZh ? `Run 完成 · ${str(d.status)}` : `Run done · ${str(d.status)}`;
  return t;
}

function recordHeadline(ev: AgentEvent, isZh: boolean): { kind: string; title: string; body: string; meta: string } {
  const d = ev.data ?? {};
  const layer = str(d.layer);
  const name = str(d.name);
  const ticker = str(d.ticker) || str(d.symbol);
  const decision = str(d.decision);
  if (ev.type === "company_deep_analysis_completed") {
    return {
      kind: isZh ? "深析" : "Deep",
      title: name || ticker || (isZh ? "未命名公司" : "Unnamed"),
      body: layer ? `${layer} · ${str(d.decision_rationale) || decision}` : str(d.decision_rationale) || decision,
      meta: decision,
    };
  }
  if (ev.type === "company_dossier_created") {
    return {
      kind: isZh ? "档案" : "Dossier",
      title: ticker || name || (isZh ? "未命名公司" : "Unnamed"),
      body: str(d.decision_rationale) || (layer ? `${layer}` : ""),
      meta: decision,
    };
  }
  // judgment_created
  const conf = d.confidence !== undefined ? Number(d.confidence).toFixed(2) : "?";
  return {
    kind: isZh ? "判断" : "Judgment",
    title: layer || (isZh ? "未命名层" : "unnamed layer"),
    body: str(d.judgment),
    meta: `${isZh ? "置信" : "Conf"} ${conf}`,
  };
}

function tsString(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function dateString(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
}

function relativeTime(ts: number, isZh: boolean): string {
  const now = Date.now() / 1000;
  const delta = Math.max(0, now - ts);
  if (delta < 60) return isZh ? "刚刚" : "just now";
  if (delta < 3600) return isZh ? `${Math.floor(delta / 60)} 分钟前` : `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return isZh ? `${Math.floor(delta / 3600)} 小时前` : `${Math.floor(delta / 3600)}h ago`;
  return isZh ? `${Math.floor(delta / 86400)} 天前` : `${Math.floor(delta / 86400)}d ago`;
}

// Pretty-print arbitrary event data for the expanded detail view.
function renderField(value: unknown): React.ReactNode {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">[]</span>;
    return (
      <ul className="live-detail-list">
        {value.map((v, i) => (
          <li key={i}>{renderField(v)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return <pre className="live-detail-pre">{JSON.stringify(value, null, 2)}</pre>;
  }
  return String(value);
}

export default function LivePage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [graph, setGraph] = useState<ThemeGraph | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [selectedThemeId, setSelectedThemeId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ThemeDetail | null>(null);
  const [themeRuns, setThemeRuns] = useState<Run[]>([]);
  const [search, setSearch] = useState("");
  const [expandedRecord, setExpandedRecord] = useState<string | null>(null);
  const [collapsedClusters, setCollapsedClusters] = useState<Set<string>>(() => new Set());
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildHint, setRebuildHint] = useState<string | null>(null);
  const [themeEvents, setThemeEvents] = useState<ThemeEvent[]>([]);
  const [ingestionSummary, setIngestionSummary] = useState<ThemeIngestionSummary | null>(null);
  const [refreshingEvents, setRefreshingEvents] = useState(false);
  const [eventsHint, setEventsHint] = useState<string | null>(null);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";

  function changeLocale(next: Locale) {
    setLocale(next);
    window.localStorage.setItem("shinkai.locale", next);
  }

  function toggleCluster(clusterId: string) {
    setCollapsedClusters((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) next.delete(clusterId);
      else next.add(clusterId);
      return next;
    });
  }

  async function handleRefreshEvents() {
    if (!selectedThemeId || refreshingEvents) return;
    setRefreshingEvents(true);
    setEventsHint(null);
    try {
      const r = await fetch(
        `${API_URL}/api/v1/themes/${selectedThemeId}/events/refresh?force=true`,
        { method: "POST", cache: "no-store" },
      );
      if (!r.ok) {
        setEventsHint(`HTTP ${r.status}`);
        return;
      }
      const summary: ThemeIngestionSummary = await r.json();
      setIngestionSummary(summary);
      if (summary.reject_reason) {
        setEventsHint(summary.reject_reason);
      } else {
        setEventsHint(
          isZh
            ? `抓到 ${summary.fetched_raw} 条 · 结构化 ${summary.structured} · 新增 ${summary.new_events}`
            : `fetched ${summary.fetched_raw} · structured ${summary.structured} · new ${summary.new_events}`,
        );
      }
      const list = await fetch(`${API_URL}/api/v1/themes/${selectedThemeId}/events`, { cache: "no-store" });
      if (list.ok) {
        const data: ThemeEventsResponse = await list.json();
        setThemeEvents(data.events);
      }
    } catch (e) {
      setEventsHint(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingEvents(false);
    }
  }

  async function handleRebuild() {
    if (rebuilding) return;
    setRebuilding(true);
    setRebuildHint(null);
    try {
      const r = await fetch(`${API_URL}/api/v1/themes/graph/rebuild`, {
        method: "POST",
        cache: "no-store",
      });
      if (!r.ok) {
        setRebuildHint(`HTTP ${r.status}`);
        return;
      }
      const data: ThemeGraph = await r.json();
      setGraph(data);
      if (data.generator !== "deepseek_llm") {
        setRebuildHint(
          isZh
            ? `回退模式 (${data.generator})${data.reject_reason ? " · " + data.reject_reason : ""}`
            : `Fell back to ${data.generator}${data.reject_reason ? " · " + data.reject_reason : ""}`,
        );
      } else {
        setRebuildHint(isZh ? "重建完成" : "Rebuilt");
      }
      const themesRes = await fetch(`${API_URL}/api/v1/themes`, { cache: "no-store" });
      if (themesRes.ok) setThemes(await themesRes.json());
    } catch (e) {
      setRebuildHint(e instanceof Error ? e.message : String(e));
    } finally {
      setRebuilding(false);
    }
  }

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
    void fetch(`${API_URL}/api/v1/auth/session`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: Session | null) => setSession(s))
      .catch(() => setSession(null));
    let cancelled = false;
    async function load() {
      try {
        const [themesRes, graphRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/themes`, { cache: "no-store" }),
          fetch(`${API_URL}/api/v1/themes/graph`, { cache: "no-store" }),
        ]);
        if (cancelled) return;
        if (themesRes.ok) {
          const data: ThemeSummary[] = await themesRes.json();
          setThemes(data);
          setSelectedThemeId((curr) => curr ?? data[0]?.theme_id ?? null);
          setError(null);
        } else {
          throw new Error(`${themesRes.status}`);
        }
        if (graphRes.ok) {
          const gdata: ThemeGraph = await graphRes.json();
          setGraph(gdata);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void load();
    const id = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  // Stable key for the themes list so the "全部" effect re-runs when the set
  // of themes changes (new theme created, latest_run_id rotated, etc.) without
  // re-running on every poll-driven object identity change.
  const themesKey = useMemo(
    () => themes.map((t) => `${t.theme_id}:${t.latest_run_id ?? ""}`).join("|"),
    [themes],
  );

  useEffect(() => {
    setExpandedRecord(null);
    let cancelled = false;

    async function loadThemeMode(themeId: string) {
      try {
        const r = await fetch(`${API_URL}/api/v1/themes/${themeId}`, { cache: "no-store" });
        if (!r.ok) throw new Error(`${r.status}`);
        const data: ThemeDetail = await r.json();
        if (cancelled) return;
        setDetail(data);
        const runs = await Promise.all(
          data.runs.slice(0, 8).map(async (r) => {
            const resp = await fetch(`${API_URL}/api/v1/runs/${r.run_id}`, { cache: "no-store" });
            if (!resp.ok) return null;
            return (await resp.json()) as Run;
          }),
        );
        if (!cancelled) setThemeRuns(runs.filter((r): r is Run => r !== null));
      } catch {
        // silent
      }
    }

    async function loadAllMode() {
      // 全部 mode: pull the latest run of every theme so the right panel can
      // aggregate analyses across the whole portfolio.
      setDetail(null);
      const ids = themes
        .map((t) => t.latest_run_id)
        .filter((id): id is string => Boolean(id));
      if (ids.length === 0) {
        if (!cancelled) setThemeRuns([]);
        return;
      }
      const runs = await Promise.all(
        ids.map(async (id) => {
          const resp = await fetch(`${API_URL}/api/v1/runs/${id}`, { cache: "no-store" });
          if (!resp.ok) return null;
          return (await resp.json()) as Run;
        }),
      );
      if (!cancelled) setThemeRuns(runs.filter((r): r is Run => r !== null));
    }

    const load = selectedThemeId ? () => loadThemeMode(selectedThemeId) : loadAllMode;
    void load();
    const id = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selectedThemeId, themesKey, themes]);

  // Theme events (real-world news + filings). Fetched when the selection
  // changes; refresh is manual (admin button) so no polling here.
  useEffect(() => {
    let cancelled = false;
    setExpandedEventId(null);
    setEventsHint(null);

    async function loadOneTheme(themeId: string) {
      try {
        const r = await fetch(`${API_URL}/api/v1/themes/${themeId}/events`, { cache: "no-store" });
        if (!r.ok) {
          if (!cancelled) {
            setThemeEvents([]);
            setIngestionSummary(null);
          }
          return;
        }
        const data: ThemeEventsResponse = await r.json();
        if (cancelled) return;
        setThemeEvents(data.events);
        setIngestionSummary(data.summary);
      } catch {
        // silent
      }
    }

    async function loadAllThemes() {
      const ids = themes.map((t) => t.theme_id);
      if (ids.length === 0) {
        if (!cancelled) {
          setThemeEvents([]);
          setIngestionSummary(null);
        }
        return;
      }
      const results = await Promise.all(
        ids.map(async (id) => {
          try {
            const r = await fetch(`${API_URL}/api/v1/themes/${id}/events`, { cache: "no-store" });
            if (!r.ok) return [];
            const data: ThemeEventsResponse = await r.json();
            return data.events;
          } catch {
            return [];
          }
        }),
      );
      if (cancelled) return;
      const merged = results.flat().sort((a, b) => b.event_ts - a.event_ts);
      setThemeEvents(merged);
      setIngestionSummary(null);
    }

    if (selectedThemeId) {
      void loadOneTheme(selectedThemeId);
    } else {
      void loadAllThemes();
    }
    return () => {
      cancelled = true;
    };
  }, [selectedThemeId, themesKey, themes]);

  const filteredThemes = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return themes;
    return themes.filter(
      (t) => t.title.toLowerCase().includes(q) || t.theme_id.toLowerCase().includes(q),
    );
  }, [themes, search]);

  // Group filtered themes by cluster, preserving the order from the graph
  // when available. Unclustered themes drop into a bucket at the end.
  const groupedThemes = useMemo<
    Array<{ id: string; name: string; rationale: string; themes: ThemeSummary[] }>
  >(() => {
    const buckets = new Map<string, { id: string; name: string; rationale: string; themes: ThemeSummary[] }>();
    const order: string[] = [];

    // Seed from graph so cluster order matches the LLM's grouping.
    if (graph) {
      for (const c of graph.clusters) {
        buckets.set(c.cluster_id, {
          id: c.cluster_id,
          name: c.cluster_name,
          rationale: c.rationale ?? "",
          themes: [],
        });
        order.push(c.cluster_id);
      }
    }

    for (const t of filteredThemes) {
      const cid = t.cluster_id ?? UNCLUSTERED_KEY;
      if (!buckets.has(cid)) {
        buckets.set(cid, {
          id: cid,
          name:
            cid === UNCLUSTERED_KEY
              ? isZh ? "未分类" : "Unclustered"
              : t.cluster_name ?? cid,
          rationale: "",
          themes: [],
        });
        order.push(cid);
      }
      buckets.get(cid)!.themes.push(t);
    }

    // Drop empty buckets (clusters whose themes were search-filtered out).
    return order
      .map((id) => buckets.get(id)!)
      .filter((b) => b.themes.length > 0);
  }, [filteredThemes, graph, isZh]);

  const isAdmin = session?.role === "admin";
  const graphGenerator = graph?.generator;

  // Flat list of every event in the theme, tagged with its run.
  const enrichedEvents = useMemo<EnrichedEvent[]>(() => {
    const out: EnrichedEvent[] = [];
    for (const r of themeRuns) {
      for (const ev of r.events) {
        out.push({ ...ev, run_id: r.id, run_status: r.status });
      }
    }
    out.sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0));
    return out;
  }, [themeRuns]);

  const milestones = useMemo(
    () => enrichedEvents.filter((e) => MILESTONE_TYPES.has(e.type)),
    [enrichedEvents],
  );

  const analyses = useMemo(
    () => enrichedEvents.filter((e) => ANALYSIS_TYPES.has(e.type)).slice().reverse(),
    [enrichedEvents],
  );

  // Map run_id → theme info so each analysis card can show which theme it
  // came from. Needed mainly for 全部 mode where records span themes.
  const runIdToTheme = useMemo<Map<string, { title: string; cluster_name: string | null }>>(() => {
    const map = new Map<string, { title: string; cluster_name: string | null }>();
    for (const t of themes) {
      if (t.latest_run_id) {
        map.set(t.latest_run_id, { title: t.title, cluster_name: t.cluster_name });
      }
    }
    if (detail) {
      const selectedCluster =
        themes.find((t) => t.theme_id === detail.theme_id)?.cluster_name ?? null;
      for (const r of detail.runs) {
        map.set(r.run_id, { title: detail.title, cluster_name: selectedCluster });
      }
    }
    return map;
  }, [themes, detail]);

  const isAllMode = selectedThemeId === null;

  const runningTotal = themes.reduce((a, t) => a + t.running_count, 0);
  const headerCounts = isZh
    ? `${themes.length} 主题 · ${themes.reduce((a, t) => a + t.run_count, 0)} 次运行${runningTotal ? ` · ${runningTotal} 在跑` : ""}`
    : `${themes.length} themes · ${themes.reduce((a, t) => a + t.run_count, 0)} runs${runningTotal ? ` · ${runningTotal} live` : ""}`;

  return (
    <PortalShell
      active="live"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "工作台" : "Workspace"}
      subtitle={
        isZh
          ? "左侧挑主题,中间看历程,右侧翻分析记录(可点开)。"
          : "Pick a theme on the left, read its journey in the middle, browse analyses on the right (click to expand)."
      }
      actions={<span className="live-workspace-counts">{headerCounts}</span>}
    >
      {error ? <p className="muted error-copy">{error}</p> : null}

      <div className="live-workspace">
        <aside className="live-themes">
          <div className="live-themes-header">
            <span className="label">{isZh ? "研究主题" : "Themes"}</span>
            <button
              type="button"
              className={`live-pill ${selectedThemeId === null ? "active" : ""}`}
              onClick={() => setSelectedThemeId(null)}
            >
              {isZh ? "全部" : "All"}
            </button>
          </div>
          {isAdmin ? (
            <div className="live-cluster-toolbar">
              <button
                type="button"
                className="live-pill"
                onClick={handleRebuild}
                disabled={rebuilding}
              >
                {rebuilding
                  ? isZh ? "重建中…" : "Rebuilding…"
                  : isZh ? "重建族群" : "Rebuild clusters"}
              </button>
              {graphGenerator && graphGenerator !== "empty" ? (
                <span className="live-cluster-meta" title={graph?.reject_reason ?? ""}>
                  {graphGenerator === "deepseek_llm"
                    ? isZh ? "LLM" : "LLM"
                    : isZh ? "回退" : "fallback"}
                </span>
              ) : null}
              {rebuildHint ? <span className="live-cluster-hint">{rebuildHint}</span> : null}
            </div>
          ) : null}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="live-search"
            placeholder={isZh ? "搜索主题…" : "Search themes…"}
            spellCheck={false}
          />
          {groupedThemes.length === 0 ? (
            <p className="muted live-empty">
              {isZh ? "没有匹配的主题。" : "No matching themes."}
            </p>
          ) : (
            <div className="live-cluster-list">
              {groupedThemes.map((bucket) => {
                const collapsed = collapsedClusters.has(bucket.id);
                return (
                  <section className="live-cluster" key={bucket.id}>
                    <button
                      type="button"
                      className="live-cluster-head"
                      onClick={() => toggleCluster(bucket.id)}
                      aria-expanded={!collapsed}
                      title={bucket.rationale || undefined}
                    >
                      <span className="live-cluster-caret" aria-hidden>
                        {collapsed ? "›" : "⌄"}
                      </span>
                      <span className="live-cluster-name">{bucket.name}</span>
                      <span className="live-cluster-count">{bucket.themes.length}</span>
                    </button>
                    {!collapsed ? (
                      <ul className="live-theme-list">
                        {bucket.themes.map((theme) => (
                          <li key={theme.theme_id}>
                            <button
                              type="button"
                              onClick={() => setSelectedThemeId(theme.theme_id)}
                              className={`live-theme-row ${selectedThemeId === theme.theme_id ? "active" : ""}`}
                            >
                              <div className="live-theme-row-title">
                                {theme.running_count > 0 ? <span className="live-pulse" aria-hidden /> : null}
                                <span>{theme.title}</span>
                              </div>
                              <div className="live-theme-row-meta">
                                <span>{theme.run_count} run</span>
                                <span>· {theme.active_hypothesis_count} {isZh ? "假设" : "hyp"}</span>
                                {theme.falsified_hypothesis_count > 0 ? (
                                  <span>· {theme.falsified_hypothesis_count} {isZh ? "证伪" : "falsified"}</span>
                                ) : null}
                                <span>· {relativeTime(theme.last_activity_ts, isZh)}</span>
                              </div>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </section>
                );
              })}
            </div>
          )}
        </aside>

        <section className="live-trace">
          <header className="live-trace-header">
            <h3>
              {isAllMode
                ? isZh ? "全部主题 · 事件流" : "All themes · Events"
                : detail?.title || (isZh ? "加载中…" : "Loading…")}
            </h3>
            <div className="live-trace-header-meta">
              <span>
                {themeEvents.length} {isZh ? "条事件" : "events"}
              </span>
              {ingestionSummary ? (
                <span title={ingestionSummary.reject_reason ?? ""}>
                  {" "}· {ingestionSummary.generator}
                </span>
              ) : null}
            </div>
            {isAdmin && !isAllMode ? (
              <div className="live-event-toolbar">
                <button
                  type="button"
                  className="live-pill"
                  onClick={handleRefreshEvents}
                  disabled={refreshingEvents}
                >
                  {refreshingEvents
                    ? isZh ? "拉取中…" : "Fetching…"
                    : isZh ? "刷新事件" : "Refresh events"}
                </button>
                {eventsHint ? <span className="live-cluster-hint">{eventsHint}</span> : null}
              </div>
            ) : null}
          </header>
          {themeEvents.length === 0 ? (
            <p className="muted live-empty">
              {isAllMode
                ? isZh ? "暂无任何主题事件。点左侧任一主题刷新拉取。" : "No events anywhere yet."
                : isAdmin
                  ? isZh ? "这个主题还没摄入,点上面的「刷新事件」拉取。" : "No events yet — click Refresh."
                  : isZh ? "这个主题还没摄入事件。" : "No events on this theme yet."}
            </p>
          ) : (
            <ul className="live-event-list">
              {themeEvents.map((ev) => {
                const isOpen = expandedEventId === ev.event_id;
                return (
                  <li key={ev.event_id} className={`live-event ${isOpen ? "open" : ""}`}>
                    <button
                      type="button"
                      className="live-event-button"
                      onClick={() => setExpandedEventId(isOpen ? null : ev.event_id)}
                      aria-expanded={isOpen}
                    >
                      <div className="live-event-row1">
                        <span className={`live-event-cat live-event-cat-${ev.category}`}>
                          {categoryLabel(ev.category, isZh)}
                        </span>
                        <span className="live-event-date">{dateString(ev.event_ts)}</span>
                        <span className="live-event-publisher" title={ev.source.url}>
                          {ev.source.publisher || (isZh ? "未知来源" : "unknown")}
                        </span>
                        <span className={`live-event-tier live-event-tier-${ev.source.tier}`}>
                          {ev.source.tier}
                        </span>
                      </div>
                      <p className="live-event-title">{ev.title}</p>
                      {ev.summary ? <p className="live-event-summary">{ev.summary}</p> : null}
                    </button>
                    {isOpen ? (
                      <div className="live-event-detail">
                        {ev.source.title && ev.source.title !== ev.title ? (
                          <div className="live-detail-row">
                            <span className="live-detail-key">{isZh ? "原标题" : "Original"}</span>
                            <div className="live-detail-value live-event-original">
                              {ev.source.title}
                            </div>
                          </div>
                        ) : null}
                        {ev.key_facts.length > 0 ? (
                          <div className="live-detail-row">
                            <span className="live-detail-key">{isZh ? "关键事实" : "Key facts"}</span>
                            <ul className="live-detail-list">
                              {ev.key_facts.map((f, i) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {ev.tickers.length > 0 ? (
                          <div className="live-detail-row">
                            <span className="live-detail-key">{isZh ? "标的" : "Tickers"}</span>
                            <div className="live-detail-value">
                              {ev.tickers.map((t) => (
                                <span className="live-event-ticker" key={t}>{t}</span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <div className="live-detail-row">
                          <span className="live-detail-key">{isZh ? "源" : "Source"}</span>
                          <div className="live-detail-value">
                            <a
                              href={ev.source.url}
                              target="_blank"
                              rel="noreferrer"
                              className="live-event-source-link"
                            >
                              {ev.source.publisher || ev.source.url}
                            </a>
                            <span className="live-event-relevance">
                              {isZh ? "相关度" : "Rel"} {(ev.relevance ?? 0).toFixed(2)}
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <aside className="live-records">
          <header className="live-records-header">
            <span className="label">{isZh ? "分析记录" : "Analyses"}</span>
            <span className="muted">
              {isAllMode
                ? `${analyses.length} · ${isZh ? "全部主题" : "all themes"}`
                : `${analyses.length}`}
            </span>
          </header>
          {analyses.length === 0 ? (
            <p className="muted live-empty">
              {isAllMode
                ? isZh ? "还没有任何分析记录。" : "No analyses anywhere yet."
                : isZh ? "这个主题还没有分析记录。" : "No analyses on this theme yet."}
            </p>
          ) : (
            <ul className="live-record-list">
              {analyses.map((ev) => {
                const key = `${ev.run_id}:${ev.event_id}`;
                const isOpen = expandedRecord === key;
                const head = recordHeadline(ev, isZh);
                const themeInfo = runIdToTheme.get(ev.run_id);
                return (
                  <li key={key} className={`live-record ${isOpen ? "open" : ""}`}>
                    <button
                      type="button"
                      className="live-record-button"
                      onClick={() => setExpandedRecord(isOpen ? null : key)}
                      aria-expanded={isOpen}
                    >
                      <div className="live-record-top">
                        <span className="live-record-kind">{head.kind}</span>
                        <span className="live-record-meta">{head.meta || dateString(ev.ts)}</span>
                      </div>
                      <p className="live-record-title">{head.title}</p>
                      {head.body ? <p className="live-record-body">{head.body}</p> : null}
                      {isAllMode && themeInfo ? (
                        <p className="live-record-theme" title={themeInfo.title}>
                          {themeInfo.cluster_name ? `${themeInfo.cluster_name} · ` : ""}
                          {themeInfo.title}
                        </p>
                      ) : null}
                    </button>
                    {isOpen ? (
                      <div className="live-record-detail">
                        {Object.entries(ev.data ?? {}).map(([k, v]) => (
                          <div className="live-detail-row" key={k}>
                            <span className="live-detail-key">{k}</span>
                            <div className="live-detail-value">{renderField(v)}</div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </aside>
      </div>
    </PortalShell>
  );
}
