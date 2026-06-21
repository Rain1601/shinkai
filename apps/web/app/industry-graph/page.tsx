import { redirect } from "next/navigation";

// /industry-graph was the original Subject workspace route. It has been
// promoted to /agent — the agent IS the workspace. Server-side redirect
// preserves bookmarks; query strings (?view=activity etc.) ride through
// untouched since redirect() carries them.
export default function IndustryGraphLegacyRedirect(): never {
  redirect("/agent");
}
