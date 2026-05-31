import type { Locale } from "../../lib/i18n";

type AgentEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

type AutonomyPanelProps = {
  events: AgentEvent[];
  locale?: Locale;
};

export function AutonomyPanel({ events, locale = "zh" }: AutonomyPanelProps) {
  const isZh = locale === "zh";
  const themes = events.filter((event) => event.type === "theme_discovered");
  const judgments = events.filter((event) => event.type === "judgment_created");
  const candidates = events.filter((event) => event.type === "candidate_created");
  const scores = events.filter((event) => event.type === "candidate_scored");
  const reviews = events.filter((event) => event.type === "review_completed");
  const evidence = events.filter((event) => event.type === "evidence_found");
  const patches = events.filter((event) => String(event.type ?? "").endsWith("_patch_proposed"));
  const tasks = events.filter((event) => event.type === "research_task_created");

  return (
    <section className="autonomy-grid">
      <AutonomyCard label={isZh ? "主题" : "Themes"} value={themes.length} tone="accent" />
      <AutonomyCard label={isZh ? "判断" : "Judgments"} value={judgments.length} tone="warn" />
      <AutonomyCard label={isZh ? "候选" : "Candidates"} value={candidates.length} tone="info" />
      <AutonomyCard label={isZh ? "评分" : "Scores"} value={scores.length} tone="gain" />
      <AutonomyCard label={isZh ? "证据" : "Evidence"} value={evidence.length} tone="accent" />
      <AutonomyCard label={isZh ? "复盘" : "Reviews"} value={reviews.length} tone="warn" />
      <AutonomyCard label={isZh ? "补丁" : "Patches"} value={patches.length} tone="info" />
      <AutonomyCard label={isZh ? "任务" : "Tasks"} value={tasks.length} tone="gain" />
    </section>
  );
}

function AutonomyCard({
  label,
  value,
  tone
}: {
  label: string;
  value: number;
  tone: "accent" | "warn" | "info" | "gain";
}) {
  return (
    <div className={`autonomy-card ${tone}`}>
      <span className="label">{label}</span>
      <strong className="numeric">{value}</strong>
    </div>
  );
}
