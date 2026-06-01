"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";
import type { Locale } from "../../lib/i18n";
import {
  localizeMode,
  localizeStage,
  localizeStatus,
  localizeText,
} from "../../lib/i18n";

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
  capabilities: ["read_results", "read_run_process"],
};

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted", "cancelled"]);

async function apiFetch(
  path: string,
  init?: RequestInit,
  adminToken?: string,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (adminToken) headers.set("Authorization", `Bearer ${adminToken}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

function eventTs(event: RunEvent): number | null {
  return typeof event.ts === "number" ? event.ts : null;
}

function lastActivityTs(run: Run): number {
  const stamps = run.events.map(eventTs).filter((ts): ts is number => ts !== null);
  return stamps.length > 0 ? Math.max(...stamps) : 0;
}

function isTerminalRun(run: Run): boolean {
  return TERMINAL_STATUSES.has(run.status);
}

function themeKey(title: string): string {
  return title.trim().toLowerCase().replace(/\s+/g, " ") || "autonomous-discovery";
}

function formatActivityTime(ts: number, locale: Locale): string {
  if (!ts) return locale === "zh" ? "暂无" : "n/a";
  return new Date(ts * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hasCapability(session: AuthSession, capability: string): boolean {
  return session.capabilities.includes(capability);
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

function groupRunsByTheme(runs: Run[], locale: Locale): ThemeGroup[] {
  const groups = new Map<string, Run[]>();
  for (const run of runs) {
    const title = localizeText(run.anchor, locale);
    const key = themeKey(title);
    groups.set(key, [...(groups.get(key) ?? []), run]);
  }
  return Array.from(groups.entries())
    .map(([key, themeRuns]) => {
      const sorted = [...themeRuns].sort((a, b) => lastActivityTs(b) - lastActivityTs(a));
      const latestRun = sorted[0];
      return {
        key,
        title: localizeText(latestRun.anchor, locale),
        runs: sorted,
        latestRun,
        runningCount: sorted.filter((run) => !isTerminalRun(run)).length,
        completedCount: sorted.filter((run) => run.status === "completed").length,
        lastActivity: lastActivityTs(latestRun),
      };
    })
    .sort((a, b) => b.lastActivity - a.lastActivity);
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [locale, setLocale] = useState<Locale>("zh");
  const [anchor, setAnchor] = useState(DEFAULT_ANCHOR_ZH);
  const [mode, setMode] = useState<Run["mode"]>("mode_b_narrative");
  const [adminToken, setAdminToken] = useState("");
  const [adminTokenInput, setAdminTokenInput] = useState("");
  const [authSession, setAuthSession] = useState<AuthSession>(DEFAULT_AUTH_SESSION);
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";
  const isAdmin = authSession.role === "admin";
  const canCreateRuns = hasCapability(authSession, "create_runs");

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
    try {
      const response = await apiFetch("/api/v1/runs", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status}`);
      setRuns((await response.json()) as Run[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadAuthSession(token = adminToken) {
    try {
      const response = await apiFetch(
        "/api/v1/auth/session",
        { cache: "no-store" },
        token,
      );
      if (!response.ok) return;
      setAuthSession((await response.json()) as AuthSession);
    } catch {
      // silent
    }
  }

  async function saveAdminToken() {
    const token = adminTokenInput.trim();
    window.localStorage.setItem("shinkai.adminToken", token);
    setAdminToken(token);
    await loadAuthSession(token);
  }

  async function clearAdminToken() {
    window.localStorage.removeItem("shinkai.adminToken");
    setAdminToken("");
    setAdminTokenInput("");
    await loadAuthSession("");
  }

  async function createRun() {
    if (!canCreateRuns) return;
    try {
      const response = await apiFetch(
        "/api/v1/runs",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode, anchor, scope: { language: locale } }),
        },
        adminToken,
      );
      if (!response.ok) return;
      const run = (await response.json()) as Run;
      setRuns((current) => [run, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function createAndStartAutonomousRun() {
    if (!canCreateRuns) return;
    try {
      const response = await apiFetch(
        "/api/v1/runs",
        {
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
              checkpoints_enabled: true,
              objective: isZh
                ? "挖掘具体、低覆盖的主题与候选公司"
                : "surface concrete under-covered themes and candidates",
            },
          }),
        },
        adminToken,
      );
      if (!response.ok) return;
      const run = (await response.json()) as Run;
      setRuns((current) => [run, ...current]);
      await apiFetch(`/api/v1/runs/${run.id}/start`, { method: "POST" }, adminToken);
      loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    const storedLocale = window.localStorage.getItem("shinkai.locale");
    if (storedLocale === "zh" || storedLocale === "en") changeLocale(storedLocale);
    const storedToken = window.localStorage.getItem("shinkai.adminToken") ?? "";
    setAdminToken(storedToken);
    setAdminTokenInput(storedToken);
    loadAuthSession(storedToken);
    loadRuns();
    const interval = window.setInterval(loadRuns, 8000);
    return () => window.clearInterval(interval);
  }, []);

  const themeGroups = useMemo(() => groupRunsByTheme(runs, locale), [runs, locale]);
  const runningRuns = runs.filter((run) => !isTerminalRun(run)).length;

  return (
    <PortalShell
      active="runs"
      locale={locale}
      title={isZh ? "自主研究" : "Autonomous Research"}
      subtitle={
        isZh
          ? "选择一个主题进入详情查看 agent 思考过程、档案、图谱与评测。"
          : "Pick a theme to inspect the agent's thinking, dossiers, graph, and eval."
      }
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
                {isZh ? "退出管理员" : "Sign out admin"}
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
                  {isZh ? "登录" : "Sign in"}
                </button>
              </>
            )}
          </div>
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
      <section className="runs-list-summary">
        <article className="surface metric-tile">
          <span className="label">{isZh ? "主题" : "Themes"}</span>
          <strong>{themeGroups.length}</strong>
        </article>
        <article className="surface metric-tile">
          <span className="label">{isZh ? "运行中" : "Running"}</span>
          <strong>{runningRuns}</strong>
        </article>
        <article className="surface metric-tile">
          <span className="label">{isZh ? "历史运行" : "Total Runs"}</span>
          <strong>{runs.length}</strong>
        </article>
      </section>

      {error ? <p className="muted error-copy">{error}</p> : null}

      <section className="theme-grid">
        {themeGroups.length === 0 ? (
          <p className="muted">
            {isZh ? "暂无主题。点上方“启动自主扫描”开始。" : "No themes yet — start an autonomous scan."}
          </p>
        ) : null}
        {themeGroups.map((group) => (
          <article className="surface theme-tile" key={group.key}>
            <header>
              <h2>{group.title}</h2>
              <span className="label">
                {isZh
                  ? `${group.runs.length} 次 · ${group.runningCount} 运行中`
                  : `${group.runs.length} runs · ${group.runningCount} active`}
              </span>
            </header>
            <p className="muted">{formatActivityTime(group.lastActivity, locale)}</p>
            <div className="theme-tile-runs">
              {group.runs.slice(0, 6).map((run, index) => (
                <Link
                  className="theme-run-chip"
                  href={`/runs/${run.id}`}
                  key={run.id}
                >
                  <span>{isZh ? `第 ${group.runs.length - index} 次` : `Run ${group.runs.length - index}`}</span>
                  <strong>{localizeStatus(run.status, locale)}</strong>
                  <small>{localizeStage(run.lifecycle_stage, locale)}</small>
                </Link>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="surface manual-run-section">
        <div className="panel-heading">
          <h2>{isZh ? "手动创建" : "Manual Create"}</h2>
        </div>
        <div className="manual-run-form">
          <label className="field compact">
            <span className="label">{isZh ? "模式" : "Mode"}</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as Run["mode"])}>
              <option value="mode_b_narrative">{localizeMode("mode_b_narrative", locale)}</option>
              <option value="mode_a_company">{localizeMode("mode_a_company", locale)}</option>
            </select>
          </label>
          <label className="field compact">
            <span className="label">{isZh ? "主题锚点" : "Anchor"}</span>
            <input value={anchor} onChange={(event) => setAnchor(event.target.value)} />
          </label>
          <button
            className="button secondary"
            disabled={!canCreateRuns}
            onClick={createRun}
            type="button"
          >
            {isZh ? "创建任务" : "Create"}
          </button>
        </div>
      </section>
    </PortalShell>
  );
}
