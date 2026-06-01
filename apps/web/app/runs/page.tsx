"use client";

import { useEffect, useState } from "react";
import { ActionPanel } from "../../components/portal/ActionPanel";
import { CheckpointBanner } from "../../components/portal/CheckpointBanner";
import { InjectPanel } from "../../components/portal/InjectPanel";
import { InjectionHistory } from "../../components/portal/InjectionHistory";
import { EventStream } from "../../components/portal/EventStream";
import { GraphPanel } from "../../components/portal/GraphPanel";
import { HypothesisCard } from "../../components/portal/HypothesisCard";
import { JudgmentPanel } from "../../components/portal/JudgmentPanel";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";
import { localizeMode, localizeStage, localizeStatus, localizeText } from "../../lib/i18n";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type Run = {
  id: string;
  mode: "mode_a_company" | "mode_b_narrative";
  anchor: string;
  status: string;
  lifecycle_stage: string;
  graph_id?: string | null;
  events: RunEvent[];
};

type AuthSession = {
  auth_required: boolean;
  role: "admin" | "subscriber" | "viewer";
  read_scope: "admin" | "subscriber" | "public";
  capabilities: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";
const DEFAULT_ANCHOR_ZH = "自主发现";
const DEFAULT_ANCHOR_EN = "Autonomous Discovery";
const DEFAULT_AUTH_SESSION: AuthSession = {
  auth_required: true,
  role: "viewer",
  read_scope: "public",
  capabilities: ["read_results", "read_run_process"]
};

async function apiFetch(
  path: string,
  init?: RequestInit,
  adminToken?: string
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (adminToken) {
    headers.set("Authorization", `Bearer ${adminToken}`);
  }
  try {
    return await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`Cannot reach Shinkai API at ${API_URL}: ${message}`);
  }
}

function upsertRun(runs: Run[], nextRun: Run): Run[] {
  const index = runs.findIndex((run) => run.id === nextRun.id);
  if (index === -1) return [nextRun, ...runs];
  return runs.map((run) => (run.id === nextRun.id ? nextRun : run));
}

function mergeRunEvent(events: RunEvent[], nextEvent: RunEvent): RunEvent[] {
  if (
    nextEvent.event_id &&
    events.some((event) => event.event_id === nextEvent.event_id)
  ) {
    return events;
  }
  if (
    !nextEvent.event_id &&
    nextEvent.ts &&
    events.some((event) => event.type === nextEvent.type && event.ts === nextEvent.ts)
  ) {
    return events;
  }
  return [...events, nextEvent];
}

function stageFromEvent(event: RunEvent, current: string): string {
  const loopIndex = event.data?.loop_index;
  if (event.type === "plan") return "planning";
  if (event.type === "supply_chain_layer_started") return `loop_${loopIndex ?? "x"}_expanding`;
  if (event.type === "review_completed") return `loop_${loopIndex ?? "x"}_review`;
  if (event.type === "optimization_decision") return `loop_${loopIndex ?? "x"}_optimize`;
  if (event.type === "eval_completed") return "evaluating";
  if (event.type === "done") return "completed";
  if (event.type === "error") return "failed";
  return current;
}

function statusFromEvent(event: RunEvent, current: string): string {
  if (event.type === "done") return "completed";
  if (event.type === "error") return "failed";
  return current;
}

function eventCount(events: RunEvent[], type: string): number {
  return events.filter((event) => event.type === type).length;
}

type ThemeGroup = {
  key: string;
  title: string;
  runs: Run[];
  latestRun: Run;
  runningCount: number;
  completedCount: number;
  lastActivity: number;
};

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted", "cancelled"]);

function eventTs(event: RunEvent): number | null {
  return typeof event.ts === "number" ? event.ts : null;
}

function firstActivityTs(run: Run): number | null {
  const timestamps = run.events.map(eventTs).filter((ts): ts is number => ts !== null);
  return timestamps.length > 0 ? Math.min(...timestamps) : null;
}

function lastActivityTs(run: Run): number {
  const timestamps = run.events.map(eventTs).filter((ts): ts is number => ts !== null);
  return timestamps.length > 0 ? Math.max(...timestamps) : 0;
}

function isTerminalRun(run: Run): boolean {
  return TERMINAL_STATUSES.has(run.status);
}

function runDurationSeconds(run: Run, nowSeconds: number): number {
  const start = firstActivityTs(run);
  if (!start) return 0;
  const end = isTerminalRun(run) ? lastActivityTs(run) || nowSeconds : nowSeconds;
  return Math.max(0, end - start);
}

function formatDuration(seconds: number, locale: Locale): string {
  const rounded = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (locale === "zh") {
    if (hours > 0) return `${hours}小时 ${minutes}分`;
    if (minutes > 0) return `${minutes}分 ${secs}秒`;
    return `${secs}秒`;
  }
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatActivityTime(ts: number, locale: Locale): string {
  if (!ts) return locale === "zh" ? "暂无" : "n/a";
  return new Date(ts * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function hasCapability(session: AuthSession, capability: string): boolean {
  return session.capabilities.includes(capability);
}

function themeKey(title: string): string {
  return title.trim().toLowerCase().replace(/\s+/g, " ") || "autonomous-discovery";
}

function sortRunsByActivity(runs: Run[]): Run[] {
  return [...runs].sort((a, b) => lastActivityTs(b) - lastActivityTs(a));
}

function groupRunsByTheme(runs: Run[], locale: Locale): ThemeGroup[] {
  const groups = new Map<string, Run[]>();
  for (const run of runs) {
    const title = localizeText(run.anchor, locale);
    const key = themeKey(title);
    groups.set(key, [...(groups.get(key) ?? []), run]);
  }
  return Array.from(groups.entries())
    .map(([key, themeRuns]) => {
      const sorted = sortRunsByActivity(themeRuns);
      const latestRun = sorted[0];
      return {
        key,
        title: localizeText(latestRun.anchor, locale),
        runs: sorted,
        latestRun,
        runningCount: sorted.filter((run) => !isTerminalRun(run)).length,
        completedCount: sorted.filter((run) => run.status === "completed").length,
        lastActivity: lastActivityTs(latestRun)
      };
    })
    .sort((a, b) => b.lastActivity - a.lastActivity);
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const [anchor, setAnchor] = useState(DEFAULT_ANCHOR_ZH);
  const [mode, setMode] = useState<Run["mode"]>("mode_b_narrative");
  const [error, setError] = useState<string | null>(null);
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const [adminToken, setAdminToken] = useState("");
  const [adminTokenInput, setAdminTokenInput] = useState("");
  const [authSession, setAuthSession] = useState<AuthSession>(DEFAULT_AUTH_SESSION);
  const isZh = locale === "zh";
  const isAdmin = authSession.role === "admin";
  const canCreateRuns = hasCapability(authSession, "create_runs");
  const canControlRuns = hasCapability(authSession, "control_runs");
  const canViewProcess = hasCapability(authSession, "read_run_process");

  function changeLocale(nextLocale: Locale) {
    setLocale(nextLocale);
    window.localStorage.setItem("shinkai.locale", nextLocale);
    setAnchor((current) => {
      if (current === DEFAULT_ANCHOR_ZH || current === DEFAULT_ANCHOR_EN) {
        return nextLocale === "zh" ? DEFAULT_ANCHOR_ZH : DEFAULT_ANCHOR_EN;
      }
      return current;
    });
  }

  async function loadRuns() {
    const response = await apiFetch("/api/v1/runs", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(isZh ? `加载运行失败：${response.status}` : `Failed to load runs: ${response.status}`);
    }
    const nextRuns: Run[] = await response.json();
    setRuns(nextRuns);
    if (!selectedRunId && nextRuns.length > 0) {
      setSelectedRunId(nextRuns[0].id);
    }
  }

  async function loadRun(runId: string) {
    const response = await apiFetch(`/api/v1/runs/${runId}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(isZh ? `加载运行失败：${response.status}` : `Failed to load run: ${response.status}`);
    }
    const run: Run = await response.json();
    setRuns((current) => upsertRun(current, run));
    return run;
  }

  async function loadAuthSession(token = adminToken) {
    const response = await apiFetch("/api/v1/auth/session", { cache: "no-store" }, token);
    if (!response.ok) {
      throw new Error(
        isZh
          ? `加载权限状态失败：${response.status}`
          : `Failed to load auth session: ${response.status}`
      );
    }
    const session: AuthSession = await response.json();
    setAuthSession(session);
    return session;
  }

  async function saveAdminToken() {
    const token = adminTokenInput.trim();
    window.localStorage.setItem("shinkai.adminToken", token);
    setAdminToken(token);
    const session = await loadAuthSession(token);
    if (session.role !== "admin") {
      setError(isZh ? "管理员 token 无效。" : "Invalid admin token.");
      return;
    }
    setError(null);
  }

  async function clearAdminToken() {
    window.localStorage.removeItem("shinkai.adminToken");
    setAdminToken("");
    setAdminTokenInput("");
    await loadAuthSession("");
  }

  async function createRun() {
    setError(null);
    if (!canCreateRuns) {
      setError(isZh ? "只读模式：需要管理员权限才能创建任务。" : "Read-only mode: admin access is required.");
      return;
    }
    try {
      const response = await apiFetch("/api/v1/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, anchor, scope: { language: locale } })
      }, adminToken);
      if (!response.ok) {
        setError(isZh ? `创建失败：${response.status}` : `Create failed: ${response.status}`);
        return;
      }
      const run: Run = await response.json();
      setRuns((current) => upsertRun(current, run));
      setSelectedRunId(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function createAndStartAutonomousRun() {
    setError(null);
    if (!canCreateRuns) {
      setError(isZh ? "只读模式：需要管理员权限才能启动扫描。" : "Read-only mode: admin access is required.");
      return;
    }
    try {
      const response = await apiFetch("/api/v1/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "mode_b_narrative",
          anchor: isZh ? DEFAULT_ANCHOR_ZH : DEFAULT_ANCHOR_EN,
          scope: {
            autonomy: true,
            max_spirals: 2,
            spiral_index: 1,
            language: locale,
            allow_live_sources: true,
            seed_domains: isZh
              ? ["AI 基础设施", "数据中心约束", "先进封装"]
              : ["AI infrastructure", "data center constraints", "advanced packaging"],
            objective: isZh
              ? "挖掘具体、低覆盖的主题与候选公司"
              : "surface concrete under-covered themes and candidates"
          }
        })
      }, adminToken);
      if (!response.ok) {
        setError(
          isZh
            ? `自主运行创建失败：${response.status}`
            : `Autonomous run create failed: ${response.status}`
        );
        return;
      }
      const run: Run = await response.json();
      setRuns((current) => upsertRun(current, run));
      setSelectedRunId(run.id);
      const startResponse = await apiFetch(
        `/api/v1/runs/${run.id}/start`,
        { method: "POST" },
        adminToken
      );
      if (!startResponse.ok) {
        setError(
          isZh
            ? `自主运行启动失败：${startResponse.status}`
            : `Autonomous run start failed: ${startResponse.status}`
        );
        return;
      }
      const startedRun: Run = await startResponse.json();
      setRuns((current) => upsertRun(current, startedRun));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function mutateRun(runId: string, action: "start" | "pause" | "abort") {
    setError(null);
    if (!canControlRuns) {
      setError(isZh ? "只读模式：需要管理员权限才能控制任务。" : "Read-only mode: admin access is required.");
      return;
    }
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/${action}`,
        { method: "POST" },
        adminToken
      );
      if (!response.ok) {
        setError(isZh ? `${action} 失败：${response.status}` : `${action} failed: ${response.status}`);
        return;
      }
      const run: Run = await response.json();
      setRuns((current) => upsertRun(current, run));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function injectIntoRun(runId: string, note: string, intent: string) {
    setError(null);
    if (!canControlRuns) {
      setError(isZh ? "只读模式：无法注入。" : "Read-only mode: cannot inject.");
      return;
    }
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/inject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note, intent }),
        },
        adminToken
      );
      if (!response.ok) {
        setError(isZh ? `注入失败：${response.status}` : `inject failed: ${response.status}`);
        return;
      }
      const run: Run = await response.json();
      setRuns((current) => upsertRun(current, run));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function resolveCheckpoint(
    runId: string,
    decision: "approve" | "reject" | "modify",
    note: string
  ) {
    setError(null);
    if (!canControlRuns) {
      setError(isZh ? "只读模式：无法处理 checkpoint。" : "Read-only mode: cannot resolve checkpoint.");
      return;
    }
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/checkpoint`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, note }),
        },
        adminToken
      );
      if (!response.ok) {
        setError(
          isZh
            ? `Checkpoint 处理失败：${response.status}`
            : `checkpoint failed: ${response.status}`
        );
        return;
      }
      const run: Run = await response.json();
      setRuns((current) => upsertRun(current, run));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    const storedLocale = window.localStorage.getItem("shinkai.locale");
    if (storedLocale === "en" || storedLocale === "zh") {
      changeLocale(storedLocale);
    }
    const storedAdminToken = window.localStorage.getItem("shinkai.adminToken") ?? "";
    setAdminToken(storedAdminToken);
    setAdminTokenInput(storedAdminToken);
    loadAuthSession(storedAdminToken).catch((err: unknown) =>
      setError(err instanceof Error ? err.message : String(err))
    );
    loadRuns().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNowSeconds(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;

    const source = new EventSource(`${API_URL}/api/v1/runs/${selectedRunId}/events`);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as RunEvent;
        setRuns((current) =>
          current.map((run) =>
            run.id === selectedRunId
              ? {
                  ...run,
                  events: mergeRunEvent(run.events, event),
                  lifecycle_stage: stageFromEvent(event, run.lifecycle_stage),
                  status: statusFromEvent(event, run.status)
                }
              : run
          )
        );
        if (event.type === "done" || event.type === "error") {
          window.setTimeout(() => {
            loadRun(selectedRunId).catch((err: unknown) =>
              setError(err instanceof Error ? err.message : String(err))
            );
          }, 250);
          source.close();
        }
        if (event.type === "child_run_created") {
          loadRuns().catch((err: unknown) =>
            setError(err instanceof Error ? err.message : String(err))
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [selectedRunId]);

  const sortedRuns = sortRunsByActivity(runs);
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? sortedRuns[0];
  const themeGroups = groupRunsByTheme(sortedRuns, locale);
  const selectedTheme = selectedRun
    ? themeGroups.find((group) => group.key === themeKey(localizeText(selectedRun.anchor, locale)))
    : undefined;
  const selectedThemeRuns = selectedTheme?.runs ?? [];
  const activeRun = sortedRuns.find((run) => !isTerminalRun(run)) ?? selectedRun;
  const runningRuns = sortedRuns.filter((run) => !isTerminalRun(run)).length;
  const selectedDuration = selectedRun
    ? formatDuration(runDurationSeconds(selectedRun, nowSeconds), locale)
    : formatDuration(0, locale);
  const activeDuration = activeRun
    ? formatDuration(runDurationSeconds(activeRun, nowSeconds), locale)
    : formatDuration(0, locale);
  const discoveryCount = selectedRun ? eventCount(selectedRun.events, "theme_discovered") : 0;
  const taskCount = selectedRun ? eventCount(selectedRun.events, "research_task_created") : 0;
  const evidenceCount = selectedRun ? eventCount(selectedRun.events, "evidence_found") : 0;
  const candidateCount = selectedRun ? eventCount(selectedRun.events, "candidate_created") : 0;
  const reviewCount = selectedRun ? eventCount(selectedRun.events, "review_completed") : 0;
  const subagentCount = selectedRun ? eventCount(selectedRun.events, "child_run_created") : 0;
  const flowSteps = [
    {
      layer: isZh ? "第一层" : "Layer 1",
      title: isZh ? "主题发现" : "Theme Discovery",
      summary: isZh
        ? "Agent 识别 AI、数据中心等大型叙事，并把可深挖主题转化为任务。"
        : "The agent detects large narratives and turns concrete themes into deep-dive tasks.",
      metric: `${discoveryCount}/${taskCount}`,
      state: discoveryCount > 0 || taskCount > 0 ? "active" : "idle"
    },
    {
      layer: isZh ? "第二层" : "Layer 2",
      title: isZh ? "深度调研" : "Deep Research",
      summary: isZh
        ? "主 Agent 或 Subagent 搜索证据、生成判断、筛选候选公司，全程记录。"
        : "The main agent or subagents collect evidence, form judgments, and screen companies with full traceability.",
      metric: `${evidenceCount}/${candidateCount}`,
      state: evidenceCount > 0 || candidateCount > 0 ? "active" : "idle"
    },
    {
      layer: isZh ? "闭环" : "Loop",
      title: isZh ? "复盘与自迭代" : "Review and Iterate",
      summary: isZh
        ? "Review/Optimize 事件决定下一轮扩展方向，必要时创建子任务继续挖掘。"
        : "Review/Optimize events decide the next frontier and can spawn follow-up runs.",
      metric: `${reviewCount}/${subagentCount}`,
      state: reviewCount > 0 || subagentCount > 0 ? "active" : "idle"
    }
  ];
  const accessLabel =
    authSession.role === "admin"
      ? isZh
        ? "管理员"
        : "Admin"
      : authSession.role === "subscriber"
        ? isZh
          ? "订阅用户"
          : "Subscriber"
        : isZh
          ? "普通用户"
          : "Viewer";
  const accessDetail =
    authSession.role === "admin"
      ? isZh
        ? "全部权限"
        : "all permissions"
      : authSession.role === "subscriber"
        ? isZh
          ? "扩展查看范围"
          : "expanded read scope"
        : isZh
          ? "可看结果与运行过程"
          : "results and run process";

  return (
    <PortalShell
      active="runs"
      locale={locale}
      subtitle={
        isZh
          ? "自主研究 Agent：发现具体主题、搜索证据、形成判断，并创建后续研究任务。"
          : "A self-directed research agent that discovers concrete themes, searches evidence, forms judgments, and opens follow-up investigations."
      }
      title={isZh ? "自主研究" : "Autonomous Research"}
      actions={
        <>
          <div className="segmented-control" aria-label={isZh ? "语言切换" : "Language"}>
            <button
              aria-pressed={locale === "zh"}
              className={locale === "zh" ? "active" : ""}
              onClick={() => changeLocale("zh")}
              type="button"
            >
              中文
            </button>
            <button
              aria-pressed={locale === "en"}
              className={locale === "en" ? "active" : ""}
              onClick={() => changeLocale("en")}
              type="button"
            >
              EN
            </button>
          </div>
          <div className="admin-auth-control">
            {isAdmin ? (
              <button className="button secondary" onClick={clearAdminToken} type="button">
                {authSession.auth_required
                  ? isZh
                    ? "退出管理员"
                    : "Sign out admin"
                  : isZh
                    ? "本地管理员"
                    : "Local admin"}
              </button>
            ) : (
              <>
                <input
                  aria-label={isZh ? "管理员 Token" : "Admin token"}
                  onChange={(event) => setAdminTokenInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void saveAdminToken();
                  }}
                  placeholder={isZh ? "管理员 token" : "admin token"}
                  type="password"
                  value={adminTokenInput}
                />
                <button className="button secondary" onClick={saveAdminToken} type="button">
                  {isZh ? "管理员登录" : "Admin Login"}
                </button>
              </>
            )}
          </div>
          <span className={`access-badge ${authSession.role}`}>
            <strong>{accessLabel}</strong>
            <span>{accessDetail}</span>
          </span>
          <button
            className="button"
            disabled={!canCreateRuns}
            onClick={createAndStartAutonomousRun}
            type="button"
          >
            {isZh ? "启动自主扫描" : "Start Autonomous Scan"}
          </button>
        </>
      }
    >
      <section className="deep-agent-layout">
        <section className="agent-dashboard-row">
          <article className="surface agent-state-card">
            <div>
              <span className="label">{isZh ? "深度挖掘 Agent" : "Deep-Mining Agent"}</span>
              <h2>{activeRun ? localizeText(activeRun.anchor, locale) : isZh ? "等待启动" : "Idle"}</h2>
              <p className="muted">
                {isZh
                  ? "先发现大型叙事主题，再创建可追踪的深度调研任务，由主 Agent 或 Subagent 持续执行。"
                  : "Discover large narrative themes first, then create traceable deep-research tasks for the main agent or subagents."}
              </p>
            </div>
            <div className="agent-state-meta">
              <span>{isZh ? "运行状态" : "Status"}</span>
              <strong>{activeRun ? localizeStatus(activeRun.status, locale) : isZh ? "空闲" : "Idle"}</strong>
              <span>{isZh ? "持续时间" : "Duration"}</span>
              <strong>{activeDuration}</strong>
            </div>
          </article>

          <div className="agent-metric-grid">
            {[
              [isZh ? "主题" : "Themes", themeGroups.length, isZh ? "可多次分析" : "repeatable"],
              [isZh ? "分析任务" : "Analyses", runs.length, isZh ? "历史运行" : "historical runs"],
              [isZh ? "运行中" : "Running", runningRuns, isZh ? "未终止任务" : "active tasks"],
              [isZh ? "事件" : "Events", selectedRun?.events.length ?? 0, isZh ? "选中任务" : "selected run"]
            ].map(([label, value, detail]) => (
              <article className="surface agent-metric-card" key={String(label)}>
                <span className="label">{label}</span>
                <strong>{value}</strong>
                <small>{detail}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="agent-workspace-grid">
          <aside className="surface theme-history-panel">
            <div className="panel-heading">
              <h2>{isZh ? "主题历史" : "Theme History"}</h2>
              <span className="label">{themeGroups.length}</span>
            </div>
            <p className="muted theme-history-copy">
              {isZh
                ? "同一主题可以被多次分析。选择主题后，中间区域会显示该主题下的单次深挖任务。"
                : "A theme can be analyzed multiple times. Select a theme to inspect its individual deep-dive runs."}
            </p>

            <div className="theme-list">
              {themeGroups.length === 0 ? (
                <p className="muted">{isZh ? "暂无主题，先启动自主扫描。" : "No themes yet. Start an autonomous scan."}</p>
              ) : null}
              {themeGroups.map((group) => (
                <button
                  className={selectedTheme?.key === group.key ? "theme-row active" : "theme-row"}
                  key={group.key}
                  onClick={() => setSelectedRunId(group.latestRun.id)}
                  type="button"
                >
                  <span className="theme-row-title">{group.title}</span>
                  <span className="theme-row-meta">
                    {isZh
                      ? `${group.runs.length} 次分析 · ${group.runningCount} 运行中`
                      : `${group.runs.length} analyses · ${group.runningCount} running`}
                  </span>
                  <span className="theme-row-foot">
                    <span>{localizeStatus(group.latestRun.status, locale)}</span>
                    <span>{formatActivityTime(group.lastActivity, locale)}</span>
                  </span>
                </button>
              ))}
            </div>

            <div className="manual-run-box">
              <span className="label">{isZh ? "手动创建深挖" : "Manual Deep Dive"}</span>
              <label className="field compact">
                <span className="label">{isZh ? "模式" : "Mode"}</span>
                <select value={mode} onChange={(event) => setMode(event.target.value as Run["mode"])}>
                  <option value="mode_b_narrative">{localizeMode("mode_b_narrative", locale)}</option>
                  <option value="mode_a_company">{localizeMode("mode_a_company", locale)}</option>
                </select>
              </label>
              <label className="field compact">
                <span className="label">{isZh ? "主题锚点" : "Theme Anchor"}</span>
                <input value={anchor} onChange={(event) => setAnchor(event.target.value)} />
              </label>
              <button
                className="button secondary"
                disabled={!canCreateRuns}
                onClick={createRun}
                type="button"
              >
                {isZh ? "创建分析任务" : "Create Analysis"}
              </button>
              {error ? <p className="muted error-copy">{error}</p> : null}
              {!canCreateRuns ? (
                <p className="muted readonly-copy">
                  {isZh
                    ? authSession.role === "subscriber"
                      ? "当前为订阅访问：可以查看更大范围的结果和运行过程，控制任务仍需管理员权限。"
                      : "当前为普通用户访问：可以查看结果和 Agent 运行过程，不能创建或控制任务。订阅后可扩大查看范围。"
                    : authSession.role === "subscriber"
                      ? "Subscriber access: expanded results and run process are visible; task controls still require admin access."
                      : "Viewer access: results and the agent run process are visible; subscription can expand the read scope."}
                </p>
              ) : null}
            </div>
          </aside>

          <section className="analysis-detail-panel">
            {selectedRun ? (
              <>
                <section className="surface analysis-header-card">
                  <div>
                    <span className="label">{isZh ? "分析任务详情" : "Analysis Detail"}</span>
                    <h2>{localizeText(selectedRun.anchor, locale)}</h2>
                    <p className="muted">
                      {localizeMode(selectedRun.mode, locale)} · {localizeStage(selectedRun.lifecycle_stage, locale)}
                    </p>
                  </div>
                  <div className="analysis-status-grid">
                    <span>
                      <small>{isZh ? "状态" : "Status"}</small>
                      <strong>{localizeStatus(selectedRun.status, locale)}</strong>
                    </span>
                    <span>
                      <small>{isZh ? "持续" : "Duration"}</small>
                      <strong>{selectedDuration}</strong>
                    </span>
                    <span>
                      <small>{isZh ? "证据" : "Evidence"}</small>
                      <strong>{evidenceCount}</strong>
                    </span>
                    <span>
                      <small>{isZh ? "候选" : "Candidates"}</small>
                      <strong>{candidateCount}</strong>
                    </span>
                  </div>
                  <div className="analysis-run-dock">
                    <span className="label">
                      {isZh ? `该主题 ${selectedThemeRuns.length} 次分析` : `${selectedThemeRuns.length} analyses`}
                    </span>
                    <div className="analysis-run-list">
                    {selectedThemeRuns.map((run, index) => (
                      <button
                        className={selectedRun.id === run.id ? "analysis-run-chip active" : "analysis-run-chip"}
                        key={run.id}
                        onClick={() => setSelectedRunId(run.id)}
                        type="button"
                      >
                        <span>{isZh ? `第 ${selectedThemeRuns.length - index} 次分析` : `Run ${selectedThemeRuns.length - index}`}</span>
                        <strong>{localizeStatus(run.status, locale)}</strong>
                        <small>{formatDuration(runDurationSeconds(run, nowSeconds), locale)}</small>
                      </button>
                    ))}
                    </div>
                  </div>
                </section>

                <section className="surface agent-flow-panel">
                  <div className="panel-heading">
                    <h2>{isZh ? "两层运行逻辑" : "Two-Layer Flow"}</h2>
                    <span className="label">{isZh ? "可观测" : "Observable"}</span>
                  </div>
                  <div className="agent-flow-grid">
                    {flowSteps.map((step) => (
                      <article className={`flow-step-card ${step.state}`} key={step.title}>
                        <span className="label">{step.layer}</span>
                        <strong>{step.title}</strong>
                        <p>{step.summary}</p>
                        <code>{step.metric}</code>
                      </article>
                    ))}
                  </div>
                </section>

                <GraphPanel
                  anchor={selectedRun.anchor}
                  graphId={selectedRun.graph_id}
                  locale={locale}
                  runId={selectedRun.id}
                />
              </>
            ) : (
              <section className="surface empty-state">
                <h2>{isZh ? "未选择分析任务" : "No Analysis Selected"}</h2>
                <p className="muted">
                  {isZh ? "启动自主扫描或创建一个深挖任务。" : "Start an autonomous scan or create a deep-dive task."}
                </p>
              </section>
            )}
          </section>

          <aside className="trace-panel">
            <ActionPanel
              disabled={!selectedRun || !canControlRuns}
              locale={locale}
              onAbort={() => selectedRun && mutateRun(selectedRun.id, "abort")}
              onPause={() => selectedRun && mutateRun(selectedRun.id, "pause")}
              onStart={() => selectedRun && mutateRun(selectedRun.id, "start")}
            />
            <InjectPanel
              disabled={!selectedRun || !canControlRuns}
              locale={locale}
              status={selectedRun?.status}
              onInject={(note, intent) =>
                selectedRun ? injectIntoRun(selectedRun.id, note, intent) : undefined
              }
              onResolveCheckpoint={(decision, note) =>
                selectedRun ? resolveCheckpoint(selectedRun.id, decision, note) : undefined
              }
            />
            <InjectionHistory events={selectedRun?.events ?? []} locale={locale} />
            <HypothesisCard events={selectedRun?.events ?? []} locale={locale} />
            {canViewProcess ? (
              <EventStream events={selectedRun?.events ?? []} locale={locale} />
            ) : (
              <section className="surface">
                <h2>{isZh ? "运行过程" : "Run Process"}</h2>
                <p className="muted">
                  {isZh ? "当前权限不可查看运行过程。" : "Current access cannot view the run process."}
                </p>
              </section>
            )}
            <JudgmentPanel events={selectedRun?.events ?? []} locale={locale} />
          </aside>
        </section>
      </section>
    </PortalShell>
  );
}
