import { PortalShell } from "../../components/portal/PortalShell";

export default function ReviewPage() {
  return (
    <PortalShell
      active="history"
      subtitle="Review blocking checkpoints before the agent continues."
      title="Checkpoint Review"
    >
      <section className="surface empty-state">
        <h2>No pending checkpoints</h2>
        <p className="muted">
          Review packets will show critic warnings, supporting evidence, counter-evidence,
          and the focused graph subview.
        </p>
      </section>
    </PortalShell>
  );
}
