import { redirect } from "next/navigation";

// /live was the first-generation "Run log viewer" surface. Its information
// has been folded into /agent:
//   - left rail (themes)          → /agent Subjects tab
//   - middle event stream         → /agent (event feed already piped)
//   - right rail (Analyses pane)  → /agent?view=activity
//
// The file is intentionally kept (rather than deleted) so any stale compiled
// bundle still resolves; the runtime export simply redirects.
export default function LiveLegacyRedirect(): never {
  redirect("/agent?view=activity");
}
