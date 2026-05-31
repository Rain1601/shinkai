"use client";

import { useEffect, useState } from "react";
import { PortalShell } from "../components/portal/PortalShell";
import type { Locale } from "../lib/i18n";
import { formatNumber, localizeDecision, localizeStatus, localizeText } from "../lib/i18n";

type PublishedCompany = {
  ticker: string;
  name: string;
  layer: string;
  decision: string;
  decision_rationale: string;
  thesis: string;
  risk_factors: string[];
  catalysts: string[];
};

type PublishedResult = {
  run_id: string;
  graph_id?: string | null;
  title: string;
  status: string;
  summary: string;
  themes: string[];
  key_findings: string[];
  companies: PublishedCompany[];
  metrics: Record<string, number | string | null>;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function HomePage() {
  const [results, setResults] = useState<PublishedResult[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const [error, setError] = useState<string | null>(null);
  const isZh = locale === "zh";

  useEffect(() => {
    const storedLocale = window.localStorage.getItem("shinkai.locale");
    if (storedLocale === "zh" || storedLocale === "en") setLocale(storedLocale);
    fetch(`${API_URL}/api/v1/results`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`results ${response.status}`);
        return response.json();
      })
      .then((payload: PublishedResult[]) => {
        setResults(payload);
        setSelectedRunId(payload[0]?.run_id ?? null);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  function changeLocale(nextLocale: Locale) {
    setLocale(nextLocale);
    window.localStorage.setItem("shinkai.locale", nextLocale);
  }

  const selected = results.find((result) => result.run_id === selectedRunId) ?? results[0];

  return (
    <PortalShell
      active="overview"
      actions={
        <>
          <div className="segmented-control" aria-label={isZh ? "语言" : "Language"}>
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
          <a className="button" href="/runs">
            {isZh ? "进入运行后台" : "Open Runs"}
          </a>
        </>
      }
      locale={locale}
      subtitle={
        isZh
          ? "普通用户查看研究结果和过程；管理员在运行页控制 Agent。"
          : "View published research results and trace; admins control agents from Runs."
      }
      title={isZh ? "研究结果" : "Published Results"}
    >
      <section className="published-layout">
        <div className="surface stack">
          <div className="panel-heading">
            <h2>{isZh ? "历史主题" : "Result History"}</h2>
            <span className="label">{results.length}</span>
          </div>
          {error ? <p className="error-copy">{error}</p> : null}
          {results.length === 0 ? (
            <p className="muted">
              {isZh ? "暂无已发布结果。先在运行页启动一次自主研究。" : "No results yet."}
            </p>
          ) : null}
          <div className="theme-list">
            {results.map((result) => (
              <button
                className={selected?.run_id === result.run_id ? "theme-row active" : "theme-row"}
                key={result.run_id}
                onClick={() => setSelectedRunId(result.run_id)}
                type="button"
              >
                <span className="theme-row-title">{localizeText(result.title, locale)}</span>
                <span className="theme-row-meta">
                  {localizeStatus(result.status, locale)} ·{" "}
                  {isZh
                    ? `${formatNumber(result.metrics.claims)} 个论点`
                    : `${formatNumber(result.metrics.claims)} claims`}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="surface stack">
          {selected ? (
            <>
              <span className="pill">{isZh ? "已发布快照" : "Published Snapshot"}</span>
              <h1>{localizeText(selected.title, locale)}</h1>
              <p className="muted">{localizeText(selected.summary, locale)}</p>
              <div className="agent-metric-grid compact">
                <Metric label={isZh ? "主题" : "Themes"} value={selected.themes.length} />
                <Metric label={isZh ? "候选" : "Candidates"} value={selected.metrics.candidates} />
                <Metric label={isZh ? "档案" : "Dossiers"} value={selected.metrics.dossiers} />
                <Metric label={isZh ? "论点" : "Claims"} value={selected.metrics.claims} />
              </div>
              <div className="published-section">
                <h2>{isZh ? "核心主题" : "Themes"}</h2>
                <div className="tag-list">
                  {selected.themes.map((theme) => (
                    <span className="pill" key={theme}>
                      {localizeText(theme, locale)}
                    </span>
                  ))}
                </div>
              </div>
              <div className="published-section">
                <h2>{isZh ? "关键判断" : "Key Findings"}</h2>
                <div className="finding-list">
                  {selected.key_findings.map((finding) => (
                    <article className="judgment-item" key={finding}>
                      <p>{localizeText(finding, locale)}</p>
                    </article>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <p className="muted">{isZh ? "等待研究结果。" : "Waiting for results."}</p>
          )}
        </div>

        <div className="surface stack">
          <div className="panel-heading">
            <h2>{isZh ? "公司线索" : "Company Leads"}</h2>
            <span className="label">{selected?.companies.length ?? 0}</span>
          </div>
          <div className="candidate-list">
            {selected?.companies.map((company) => (
              <article className="candidate-chip" key={`${company.ticker}-${company.layer}`}>
                <strong>
                  {company.ticker} · {localizeDecision(company.decision, locale)}
                </strong>
                <span>{company.name}</span>
                <span>{localizeText(company.layer, locale)}</span>
                <span>{localizeText(company.decision_rationale, locale)}</span>
              </article>
            ))}
          </div>
        </div>
      </section>
    </PortalShell>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="agent-metric-card metric-tile">
      <small>{label}</small>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}
