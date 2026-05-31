import type { Locale } from "../../lib/i18n";

type ActionPanelProps = {
  onStart?: () => void;
  onPause?: () => void;
  onAbort?: () => void;
  disabled?: boolean;
  locale?: Locale;
};

export function ActionPanel({
  onStart,
  onPause,
  onAbort,
  disabled,
  locale = "zh"
}: ActionPanelProps) {
  const isZh = locale === "zh";
  return (
    <section className="surface action-panel">
      <div className="panel-heading">
        <h2>{isZh ? "自主 Agent" : "Autonomous Agent"}</h2>
      </div>
      <div className="control-grid">
        <button className="button" disabled={disabled} onClick={onStart} type="button">
          {isZh ? "运行自主扫描" : "Run Autonomous Scan"}
        </button>
        <button className="button secondary" disabled={disabled} onClick={onPause} type="button">
          {isZh ? "暂停" : "Pause"}
        </button>
        <button className="button danger" disabled={disabled} onClick={onAbort} type="button">
          {isZh ? "终止" : "Abort"}
        </button>
      </div>
      <div className="review-card">
        <span className="label">{isZh ? "默认姿态" : "Default posture"}</span>
        <strong>{isZh ? "自主发现" : "Self-directed discovery"}</strong>
        <p className="muted">
          {isZh
            ? "Agent 会主动选择具体主题、搜索证据、形成判断，并创建后续研究任务。"
            : "The agent should pick concrete themes, search, form judgments, and open research tasks without waiting for human scoping."}
        </p>
      </div>
    </section>
  );
}
