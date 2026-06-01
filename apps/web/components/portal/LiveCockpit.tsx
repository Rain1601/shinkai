import Link from "next/link";
import type { Locale } from "../../lib/i18n";
import { formatNumber, localizeStatus, localizeText } from "../../lib/i18n";

type LiveEvent = {
  event_id: string;
  type: string;
  ts: number | null;
  summary: string;
};

type LiveRun = {
  run_id: string;
  anchor: string;
  status: string;
  lifecycle_stage: string;
  elapsed_seconds: number;
  judgment: {
    hypothesis_id: string | null;
    layer: string;
    judgment: string;
    confidence: number | null;
  } | null;
  recent_events: LiveEvent[];
};

type LiveCockpitProps = {
  run: LiveRun;
  locale: Locale;
  label?: string;
};

function elapsedLabel(seconds: number, isZh: boolean): string {
  if (!seconds) return isZh ? "刚启动" : "starting";
  if (seconds < 60) return isZh ? `${Math.floor(seconds)} 秒` : `${Math.floor(seconds)}s`;
  if (seconds < 3600)
    return isZh ? `${Math.floor(seconds / 60)} 分钟` : `${Math.floor(seconds / 60)}m`;
  return isZh ? `${Math.floor(seconds / 3600)} 小时` : `${Math.floor(seconds / 3600)}h`;
}

export function LiveCockpit({ run, locale, label }: LiveCockpitProps) {
  const isZh = locale === "zh";
  return (
    <article className="live-flat">
      <header className="live-flat-eyebrow">
        <span className="label">
          {label ?? (isZh ? "实时驾驶舱" : "Live cockpit")}
        </span>
        <span className="live-flat-status">
          {localizeStatus(run.status, locale)} · {elapsedLabel(run.elapsed_seconds, isZh)}
        </span>
      </header>

      <h2 className="live-flat-anchor">
        {localizeText(run.anchor, locale)}
        <code>#{run.run_id.slice(0, 8)}</code>
      </h2>

      <section className="live-flat-judgment">
        <span className="label">{isZh ? "当前判断" : "Current judgment"}</span>
        {run.judgment ? (
          <>
            <p className="live-flat-layer">
              {run.judgment.layer || (isZh ? "未命名层" : "unnamed layer")}
            </p>
            <p className="live-flat-claim">{run.judgment.judgment}</p>
            {run.judgment.confidence !== null ? (
              <p className="live-flat-confidence">
                <span>{isZh ? "置信度" : "Confidence"}</span>
                <strong>{formatNumber(run.judgment.confidence)}</strong>
              </p>
            ) : null}
          </>
        ) : (
          <p className="muted">{isZh ? "尚未形成判断。" : "No judgment yet."}</p>
        )}
      </section>

      <section className="live-flat-events">
        <span className="label">{isZh ? "最近事件" : "Recent events"}</span>
        {run.recent_events.length === 0 ? (
          <p className="muted">{isZh ? "暂无事件。" : "No events yet."}</p>
        ) : (
          <ol>
            {run.recent_events.map((event) => (
              <li key={event.event_id}>
                <code>{event.type}</code>
                <span>{event.summary}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <footer className="live-flat-footer">
        <Link className="link-button" href={`/runs/${run.run_id}?tab=cockpit`}>
          {isZh ? "进入完整 Cockpit" : "Open full cockpit"} →
        </Link>
      </footer>
    </article>
  );
}
