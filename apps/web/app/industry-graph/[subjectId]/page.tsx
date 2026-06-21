import { redirect } from "next/navigation";

// Promoted to /agent/[subjectId]. Preserve bookmarks via server-side
// redirect; the use() call resolves the route param so we can rebuild
// the target URL.
export default async function IndustryGraphSubjectLegacyRedirect({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}): Promise<never> {
  const { subjectId } = await params;
  redirect(`/agent/${subjectId}`);
}
