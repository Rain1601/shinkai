"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CockpitTab } from "../../../components/portal/CockpitTab";
import { DossierTab } from "../../../components/portal/DossierTab";
import { EvalTab } from "../../../components/portal/EvalTab";
import { GraphTab } from "../../../components/portal/GraphTab";
import { PlannerBadge } from "../../../components/portal/PlannerBadge";
import { PortalShell } from "../../../components/portal/PortalShell";
import { ReasoningTreeView } from "../../../components/portal/ReasoningTreeView";
import { RecapCard } from "../../../components/portal/RecapCard";
import type { Locale } from "../../../lib/i18n";
import {
  localizeMode,
  localizeStage,
  localizeStatus,
  localizeText,
} from "../../../lib/i18n";
import { useLastSeen } from "../../../lib/useLastSeen";

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

type TabId = "framework" | "cockpit" | "dossier" | "graph" | "eval";

const TABS: { id: TabId; zh: string; en: string }[] = [
  { id: "framework", zh: "框架", en: "Framework" },
  { id: "cockpit", zh: "驾驶舱", en: "Cockpit" },
  { id: "dossier", zh: "档案", en: "Dossier" },
  { id: "graph", zh: "图谱", en: "Graph" },
  { id: "eval", zh: "评测", en: "Eval" },
];

const TAB_STORAGE_KEY = "shinkai.runTab.default";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";
const DEFAULT_AUTH_SESSION: AuthSession = {
  auth_required: true,
  role: "viewer",
  read_scope: "public",
  capabilities: ["read_results", "read_run_process"],
};

async function apiFetch(
  path: string,
  init?: RequestInit,
  adminToken?: string,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (adminToken) headers.set("Authorization", `Bearer ${adminToken}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

function mergeRunEvent(events: RunEvent[], nextEvent: RunEvent): RunEvent[] {
  if (nextEvent.event_id && events.some((event) => event.event_id === nextEvent.event_id)) {
    return events;
  }
  return [...events, nextEvent];
}

function hasCapability(session: AuthSession, capability: string): boolean {
  return session.capabilities.includes(capability);
}

function isValidTab(value: string | null): value is TabId {
  return (
    value === "framework" ||
    value === "cockpit" ||
    value === "dossier" ||
    value === "graph" ||
    value === "eval"
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const router = useRouter();
  const searchParams = useSearchParams();
  const [locale, setLocale] = useState<Locale>("zh");
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adminToken, setAdminToken] = useState("");
  const [authSession, setAuthSession] = useState<AuthSession>(DEFAULT_AUTH_SESSION);

  const isZh = locale === "zh";
  const canControlRuns = hasCapability(authSession, "control_runs");
  const canViewProcess = hasCapability(authSession, "read_run_process");

  const initialTab = useMemo<TabId>(() => {
    const urlTab = searchParams.get("tab");
    if (isValidTab(urlTab)) return urlTab;
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(TAB_STORAGE_KEY);
      if (isValidTab(stored)) return stored;
    }
    return "framework";
  }, [searchParams]);

  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  function switchTab(tab: TabId) {
    setActiveTab(tab);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TAB_STORAGE_KEY, tab);
      const params = new URLSearchParams(window.location.search);
      params.set("tab", tab);
      router.replace(`/runs/${runId}?${params.toString()}`, { scroll: false });
    }
  }

  async function loadRun() {
    try {
      const response = await apiFetch(`/api/v1/runs/${runId}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${response.status}`);
      }
      setRun((await response.json()) as Run);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadAuthSession(token: string) {
    try {
      const response = await apiFetch("/api/v1/auth/session", { cache: "no-store" }, token);
      if (!response.ok) return;
      setAuthSession((await response.json()) as AuthSession);
    } catch {
      // silent
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedLocale = window.localStorage.getItem("shinkai.locale");
    if (storedLocale === "zh" || storedLocale === "en") setLocale(storedLocale);
    const storedAdminToken = window.localStorage.getItem("shinkai.adminToken") ?? "";
    setAdminToken(storedAdminToken);
    loadAuthSession(storedAdminToken);
    loadRun();
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    const source = new EventSource(`${API_URL}/api/v1/runs/${runId}/events`);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as RunEvent;
        setRun((current) =>
          current
            ? {
                ...current,
                events: mergeRunEvent(current.events, event),
                status:
                  event.type === "done"
                    ? "completed"
                    : event.type === "error"
                      ? "failed"
                      : current.status,
              }
            : current,
        );
        if (event.type === "done" || event.type === "error") {
          window.setTimeout(() => loadRun(), 250);
          source.close();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId]);

  async function mutateRun(action: "start" | "pause" | "abort") {
    if (!canControlRuns) return;
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/${action}`,
        { method: "POST" },
        adminToken,
      );
      if (response.ok) {
        setRun((await response.json()) as Run);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function injectIntoRun(note: string, intent: string) {
    if (!canControlRuns) return;
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/inject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note, intent }),
        },
        adminToken,
      );
      if (response.ok) {
        setRun((await response.json()) as Run);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function resolveCheckpoint(
    decision: "approve" | "reject" | "modify",
    note: string,
  ) {
    if (!canControlRuns) return;
    try {
      const response = await apiFetch(
        `/api/v1/runs/${runId}/checkpoint`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, note }),
        },
        adminToken,
      );
      if (response.ok) {
        setRun((await response.json()) as Run);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const events = run?.events ?? [];
  const { lastSeen } = useLastSeen(runId ? `run:${runId}` : null);

  return (
    <PortalShell
      active="history"
      locale={locale}
      title={run ? localizeText(run.anchor, locale) : isZh ? "运行详情" : "Run Detail"}
      subtitle={
        run
          ? `${localizeMode(run.mode, locale)} · ${localizeStatus(run.status, locale)} · ${localizeStage(run.lifecycle_stage, locale)}`
          : undefined
      }
      actions={
        <Link className="button secondary" href="/runs">
          {isZh ? "← 返回列表" : "← Back"}
        </Link>
      }
    >
      <div className="run-meta-row">
        <PlannerBadge events={events} locale={locale} />
      </div>

      <RecapCard events={events} lastSeen={lastSeen} locale={locale} />

      <nav className="run-tabs" aria-label={isZh ? "运行视图" : "Run views"}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={tab.id === activeTab ? "run-tab active" : "run-tab"}
            onClick={() => switchTab(tab.id)}
            aria-pressed={tab.id === activeTab}
          >
            {isZh ? tab.zh : tab.en}
          </button>
        ))}
      </nav>

      {error ? <p className="muted error-copy">{error}</p> : null}

      {run ? (
        <div className="run-detail-body">
          {activeTab === "framework" ? (
            <ReasoningTreeView
              runId={run.id}
              locale={locale}
              refreshSignal={events.length}
            />
          ) : null}
          {activeTab === "cockpit" && canViewProcess ? (
            <CockpitTab
              runId={run.id}
              status={run.status}
              events={events}
              locale={locale}
              canControlRuns={canControlRuns}
              lastSeen={lastSeen}
              onInject={injectIntoRun}
              onResolveCheckpoint={resolveCheckpoint}
            />
          ) : null}
          {activeTab === "cockpit" && !canViewProcess ? (
            <p className="muted">
              {isZh ? "当前权限不可查看运行过程。" : "Current access cannot view the run process."}
            </p>
          ) : null}
          {activeTab === "dossier" ? (
            <DossierTab
              events={events}
              locale={locale}
              canControlRuns={canControlRuns}
              onStart={() => mutateRun("start")}
              onPause={() => mutateRun("pause")}
              onAbort={() => mutateRun("abort")}
            />
          ) : null}
          {activeTab === "graph" ? (
            <GraphTab
              runId={run.id}
              anchor={run.anchor}
              graphId={run.graph_id ?? null}
              locale={locale}
            />
          ) : null}
          {activeTab === "eval" ? <EvalTab events={events} locale={locale} /> : null}
        </div>
      ) : (
        <p className="muted">{isZh ? "加载中…" : "Loading…"}</p>
      )}
    </PortalShell>
  );
}
