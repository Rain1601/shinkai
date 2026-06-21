import { redirect } from "next/navigation";

// /live was the first-generation "Run log viewer" surface. Its information
// has been folded into /industry-graph:
//   - left rail (themes)          → /industry-graph Subjects tab
//   - middle event stream         → /industry-graph (event feed already piped)
//   - right rail (Analyses pane)  → /industry-graph?view=activity
//
// The file is intentionally kept (rather than deleted) so any stale compiled
// bundle still resolves; the runtime export simply redirects.
export default function LiveLegacyRedirect(): never {
  redirect("/industry-graph?view=activity");
}
