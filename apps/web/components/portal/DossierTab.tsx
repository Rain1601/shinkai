import type { Locale } from "../../lib/i18n";
import { localizeDecision, localizeText } from "../../lib/i18n";
import { ActionPanel } from "./ActionPanel";
import { JudgmentPanel } from "./JudgmentPanel";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type DossierTabProps = {
  events: RunEvent[];
  locale: Locale;
  canControlRuns: boolean;
  onStart: () => void;
  onPause: () => void;
  onAbort: () => void;
};

export function DossierTab({
  events,
  locale,
  canControlRuns,
  onStart,
  onPause,
  onAbort,
}: DossierTabProps) {
  const isZh = locale === "zh";
  const dossiers = events.filter((event) => event.type === "company_dossier_created");

  return (
    <div className="dossier-tab">
      <ActionPanel
        disabled={!canControlRuns}
        locale={locale}
        onStart={onStart}
        onPause={onPause}
        onAbort={onAbort}
      />
      <JudgmentPanel events={events} locale={locale} />
      <section className="surface dossier-list">
        <div className="panel-heading">
          <h2>{isZh ? "公司档案" : "Company Dossiers"}</h2>
          <span className="label">{dossiers.length}</span>
        </div>
        {dossiers.length === 0 ? (
          <p className="muted">
            {isZh ? "暂无档案。" : "No dossiers yet."}
          </p>
        ) : null}
        <div className="dossier-grid">
          {dossiers.map((event, index) => {
            const data = event.data ?? {};
            const ticker = String(data.ticker ?? "");
            const decision = localizeDecision(data.decision, locale);
            const rationale = localizeText(data.decision_rationale ?? "", locale);
            const layer = localizeText(data.layer ?? "", locale);
            const risks = Array.isArray(data.risk_factors)
              ? (data.risk_factors as unknown[]).map((value) => String(value))
              : [];
            const catalysts = Array.isArray(data.catalysts)
              ? (data.catalysts as unknown[]).map((value) => String(value))
              : [];
            return (
              <article className="dossier-card" key={`${ticker}-${index}`}>
                <header>
                  <strong>{ticker || (isZh ? "候选" : "Candidate")}</strong>
                  <span className="pill">{decision}</span>
                </header>
                {layer ? <p className="muted">{layer}</p> : null}
                {rationale ? <p>{rationale}</p> : null}
                {risks.length > 0 ? (
                  <div className="dossier-list-block">
                    <span className="label">{isZh ? "风险" : "Risks"}</span>
                    <ul>
                      {risks.map((risk, riskIndex) => (
                        <li key={riskIndex}>{localizeText(risk, locale)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {catalysts.length > 0 ? (
                  <div className="dossier-list-block">
                    <span className="label">{isZh ? "催化剂" : "Catalysts"}</span>
                    <ul>
                      {catalysts.map((cat, catIndex) => (
                        <li key={catIndex}>{localizeText(cat, locale)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
