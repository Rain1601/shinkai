import type { Locale } from "../../lib/i18n";
import { localizeStage, localizeStatus } from "../../lib/i18n";

type RunProgressProps = {
  status: string;
  stage: string;
  events: number;
  locale?: Locale;
};

const stages = ["created", "scoped", "graph_expansion", "underwriting", "review", "completed"];

export function RunProgress({ status, stage, events, locale = "zh" }: RunProgressProps) {
  const isZh = locale === "zh";
  const currentIndex = Math.max(0, stages.indexOf(stage));

  return (
    <section className="surface run-progress" aria-label={isZh ? "运行进度" : "Run progress"}>
      <div>
        <span className="label">{isZh ? "状态" : "Status"}</span>
        <strong>{localizeStatus(status, locale)}</strong>
      </div>
      <div>
        <span className="label">{isZh ? "阶段" : "Stage"}</span>
        <strong>{localizeStage(stage, locale)}</strong>
      </div>
      <div>
        <span className="label">{isZh ? "事件" : "Events"}</span>
        <strong>{events}</strong>
      </div>
      <div className="stage-track" aria-hidden="true">
        {stages.map((item, index) => (
          <span className={index <= currentIndex ? "stage-dot active" : "stage-dot"} key={item} />
        ))}
      </div>
    </section>
  );
}
