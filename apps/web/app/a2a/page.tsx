import { PortalShell } from "../../components/portal/PortalShell";

export default function A2APage() {
  return (
    <PortalShell
      active="a2a"
      subtitle="Structured handoffs and feedback between shinkai and uteki."
      title="A2A Messages"
    >
      <section className="surface empty-state">
        <h2>No messages</h2>
        <p className="muted">
          Candidate handoffs, monitoring feedback, claim challenges, and patch proposals
          will appear here.
        </p>
      </section>
    </PortalShell>
  );
}
