import { redirect } from "next/navigation";

// /actions was the Mode B agent control panel (Triggers matrix, Critic
// personas, Memory layers, Patch inbox). In the Subject-centric world the
// equivalents live per-Subject (schedule on the Subject record, critic
// verdicts on each SubjectVersion, agent-proposed patches inline in
// Activity), so the standalone page no longer earns its slot in the
// primary nav.
//
// The component files under apps/web/components/portal/ (TriggersMatrix,
// CriticPersonas, MemoryLayers, PatchInbox) are retained for reference and
// can be re-mounted if/when the surface needs to come back.
export default function ActionsLegacyRedirect(): never {
  redirect("/industry-graph");
}
