import type { Locale } from "../../lib/i18n";

type Heartrate = {
  total_runs: number;
  active_runs: number;
  awaiting_checkpoints: number;
  completed_runs: number;
  failed_runs: number;
  total_hypotheses: number;
  active_hypotheses: number;
  falsified_hypotheses: number;
  total_dossiers: number;
  total_patches_proposed: number;
  total_critic_verdicts: number;
  total_critic_rejects: number;
  total_injections: number;
  total_spirals: number;
};

type AgentHeartrateProps = {
  heartrate: Heartrate;
  sinceFirstActivityTs: number | null;
  locale: Locale;
};

type Tile = {
  labelZh: string;
  labelEn: string;
  value: number | string;
  noteZh?: string;
  noteEn?: string;
};

function formatDate(ts: number | null, locale: Locale): string {
  if (!ts) return locale === "zh" ? "—" : "—";
  return new Date(ts * 1000).toLocaleDateString(
    locale === "zh" ? "zh-CN" : "en-US",
    { year: "numeric", month: "short", day: "numeric" },
  );
}

export function AgentHeartrate({
  heartrate,
  sinceFirstActivityTs,
  locale,
}: AgentHeartrateProps) {
  const isZh = locale === "zh";
  const falsifiedRate =
    heartrate.total_hypotheses > 0
      ? Math.round((heartrate.falsified_hypotheses / heartrate.total_hypotheses) * 100)
      : 0;
  const tiles: Tile[] = [
    {
      labelEn: "Total runs",
      labelZh: "累计 run",
      value: heartrate.total_runs,
      noteEn: `${heartrate.completed_runs} completed · ${heartrate.failed_runs} failed`,
      noteZh: `${heartrate.completed_runs} 完成 · ${heartrate.failed_runs} 失败`,
    },
    {
      labelEn: "Active",
      labelZh: "活跃中",
      value: heartrate.active_runs,
      noteEn: `${heartrate.awaiting_checkpoints} awaiting review`,
      noteZh: `${heartrate.awaiting_checkpoints} 待审阅`,
    },
    {
      labelEn: "Hypotheses",
      labelZh: "假设",
      value: heartrate.total_hypotheses,
      noteEn: `${heartrate.active_hypotheses} active · ${heartrate.falsified_hypotheses} falsified`,
      noteZh: `${heartrate.active_hypotheses} 活跃 · ${heartrate.falsified_hypotheses} 证伪`,
    },
    {
      labelEn: "Falsified",
      labelZh: "证伪率",
      value: `${falsifiedRate}%`,
      noteEn: "of total hypotheses",
      noteZh: "占假设总数",
    },
    {
      labelEn: "Dossiers",
      labelZh: "公司档案",
      value: heartrate.total_dossiers,
      noteEn: `${heartrate.total_critic_rejects} critic rejects`,
      noteZh: `${heartrate.total_critic_rejects} 评审否决`,
    },
    {
      labelEn: "Self-iteration",
      labelZh: "自我迭代",
      value: heartrate.total_patches_proposed,
      noteEn: `${heartrate.total_spirals} child spirals`,
      noteZh: `${heartrate.total_spirals} 子 spiral`,
    },
    {
      labelEn: "Human injections",
      labelZh: "人工注入",
      value: heartrate.total_injections,
      noteEn: "via inject endpoint",
      noteZh: "经由 inject 接口",
    },
  ];

  return (
    <section className="surface agent-heartrate">
      <div className="panel-heading">
        <h2>{isZh ? "心率" : "Heartrate"}</h2>
        <span className="label">
          {isZh ? "自首次活动" : "Since first activity"} ·{" "}
          {formatDate(sinceFirstActivityTs, locale)}
        </span>
      </div>
      <div className="agent-heartrate-grid">
        {tiles.map((tile) => (
          <article className="agent-heartrate-tile" key={isZh ? tile.labelZh : tile.labelEn}>
            <span className="label">{isZh ? tile.labelZh : tile.labelEn}</span>
            <strong>{tile.value}</strong>
            <small>{isZh ? tile.noteZh : tile.noteEn}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
