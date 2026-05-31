import { GraphPanel } from "../../components/portal/GraphPanel";
import { PortalShell } from "../../components/portal/PortalShell";

export default function GraphPage() {
  return (
    <PortalShell
      active="graph"
      subtitle="Inspect claims, evidence, questions, and thesis nodes."
      title="Research Graph"
    >
      <GraphPanel anchor="Select a run" graphId={null} />
    </PortalShell>
  );
}
