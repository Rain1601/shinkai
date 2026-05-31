"use client";

import { useEffect, useState } from "react";
import { PortalShell } from "../../components/portal/PortalShell";

type Run = {
  id: string;
  anchor: string;
  status: string;
  events: Array<{ type?: string }>;
};

type EvalFinding = {
  severity: string;
  target_ref: string;
  message: string;
};

type EvalReport = {
  run_id: string;
  process_score: number | null;
  evidence_score: number | null;
  reasoning_score: number | null;
  discovery_score: number | null;
  findings: EvalFinding[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function EvalPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/runs`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`runs ${response.status}`);
        return response.json();
      })
      .then((payload: Run[]) => {
        setRuns(payload);
        const completed = payload.find((run) => run.status === "completed") ?? payload[0];
        if (completed) setSelectedRunId(completed.id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    fetch(`${API_URL}/api/v1/eval/runs/${selectedRunId}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`eval ${response.status}`);
        return response.json();
      })
      .then((payload: EvalReport) => {
        setReport(payload);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedRunId]);

  return (
    <PortalShell
      active="eval"
      subtitle="Trace-native process, evidence, reasoning, and discovery evaluation."
      title="Eval Reports"
    >
      <section className="grid">
        <div className="surface stack">
          <span className="label">Run</span>
          <h2>Evaluated Run</h2>
          {runs.length === 0 ? <p className="muted">No runs yet.</p> : null}
          <div className="run-list">
            {runs.map((run) => (
              <button
                className={selectedRunId === run.id ? "run-card active" : "run-card"}
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                type="button"
              >
                <strong>{run.anchor}</strong>
                <span>
                  {run.status} · {run.events.length} events
                </span>
              </button>
            ))}
          </div>
          {error ? <p className="muted">{error}</p> : null}
        </div>

        <div className="surface stack">
          <span className="label">Scores</span>
          <h2>Trace Eval</h2>
          {report ? (
            <div className="eval-score-grid">
              <Score label="Process" value={report.process_score} />
              <Score label="Evidence" value={report.evidence_score} />
              <Score label="Reasoning" value={report.reasoning_score} />
              <Score label="Discovery" value={report.discovery_score} />
            </div>
          ) : (
            <p className="muted">Select a completed run.</p>
          )}
        </div>
      </section>

      <section className="surface stack eval-findings">
        <div className="panel-heading">
          <h2>Findings</h2>
          <span className="label">{report?.findings.length ?? 0}</span>
        </div>
        {report?.findings.length === 0 ? <p className="muted">No findings.</p> : null}
        {report?.findings.map((finding, index) => (
          <article className="judgment-item" key={`${finding.target_ref}-${index}`}>
            <strong>{finding.severity}</strong>
            <p>{finding.message}</p>
          </article>
        ))}
      </section>
    </PortalShell>
  );
}

function Score({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="autonomy-card accent">
      <span className="label">{label}</span>
      <strong className="numeric">{value === null ? "n/a" : Math.round(value * 100)}</strong>
    </div>
  );
}
