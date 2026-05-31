import { PortalShell } from "../components/portal/PortalShell";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export default function HomePage() {
  return (
    <PortalShell
      active="overview"
      subtitle="Discovery, company analysis, checkpoint review, and A2A handoff."
      title="Shinkai Portal"
      actions={
        <a className="button" href="/runs">
          Open Runs
        </a>
      }
    >
      <section className="grid">
        <div className="surface stack">
          <span className="pill">Agent = Model + Harness</span>
          <h1>Long-running research, observable by design.</h1>
          <p className="muted">
            Shinkai is structured around runs, events, research graphs,
            checkpoints, eval reports, and A2A handoffs to uteki.
          </p>
        </div>
        <div className="surface stack">
          <h2>Backend</h2>
          <p className="muted">FastAPI API target:</p>
          <code>{API_URL}</code>
          <p className="muted">Next slice: connect this UI to `/api/v1/runs` and SSE events.</p>
        </div>
      </section>
    </PortalShell>
  );
}
