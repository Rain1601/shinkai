import type { Locale } from "../../lib/i18n";

type AgentIdentityProps = {
  name: string;
  chineseName: string;
  taglineEn: string;
  taglineZh: string;
  version: string;
  status: "idle" | "running" | "awaiting_checkpoint";
  lastActivityTs: number | null;
  locale: Locale;
};

function statusLabel(
  status: AgentIdentityProps["status"],
  isZh: boolean,
): string {
  if (status === "running") return isZh ? "运行中" : "running";
  if (status === "awaiting_checkpoint") return isZh ? "等待审阅" : "awaiting review";
  return isZh ? "空闲" : "idle";
}

function elapsedLabel(ts: number | null, isZh: boolean): string {
  if (!ts) return isZh ? "尚未活动" : "never active";
  const now = Math.floor(Date.now() / 1000);
  const delta = Math.max(0, now - ts);
  if (delta < 60) return isZh ? `${delta} 秒前` : `${delta}s ago`;
  if (delta < 3600) return isZh ? `${Math.floor(delta / 60)} 分钟前` : `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return isZh ? `${Math.floor(delta / 3600)} 小时前` : `${Math.floor(delta / 3600)}h ago`;
  return isZh ? `${Math.floor(delta / 86400)} 天前` : `${Math.floor(delta / 86400)}d ago`;
}

export function AgentIdentity({
  name,
  chineseName,
  taglineEn,
  taglineZh,
  version,
  status,
  lastActivityTs,
  locale,
}: AgentIdentityProps) {
  const isZh = locale === "zh";
  const tagline = isZh ? taglineZh : taglineEn;
  return (
    <section className="surface agent-identity">
      <div className="agent-identity-left">
        <div className="agent-identity-marks">
          <h1 className="agent-identity-name">{name}</h1>
          <span className="agent-identity-cn">{chineseName}</span>
        </div>
        <p className="agent-identity-tagline">{tagline}</p>
        <div className="agent-identity-meta">
          <span className="label">{isZh ? "版本" : "Version"} · {version}</span>
        </div>
      </div>
      <div className="agent-identity-right">
        <span className={`agent-status-pill agent-status-${status}`}>
          {statusLabel(status, isZh)}
        </span>
        <span className="agent-identity-elapsed">
          {isZh ? "上次活动" : "Last active"} · {elapsedLabel(lastActivityTs, isZh)}
        </span>
      </div>
    </section>
  );
}
