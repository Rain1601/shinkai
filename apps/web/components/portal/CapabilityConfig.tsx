import type { Locale } from "../../lib/i18n";

type Trigger = {
  key: string;
  name_en: string;
  name_zh: string;
  default: unknown;
  description_en: string;
  description_zh: string;
  options: unknown[];
};

type CapabilityConfigProps = {
  triggers: Trigger[];
  locale: Locale;
};

function formatDefault(value: unknown): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "—";
  return String(value);
}

export function CapabilityConfig({ triggers, locale }: CapabilityConfigProps) {
  const isZh = locale === "zh";
  return (
    <section className="surface capability-config">
      <div className="panel-heading">
        <h2>{isZh ? "能力装备" : "Capabilities"}</h2>
        <span className="label">{triggers.length}</span>
      </div>
      <p className="muted capability-config-intro">
        {isZh
          ? "Agent 默认开启的 trigger 与可调标志。每次创建 run 时可在 scope 里覆盖。"
          : "Default triggers and flags. Each run can override these via its scope."}
      </p>
      <div className="capability-list">
        {triggers.map((trigger) => (
          <article className="capability-row" key={trigger.key}>
            <header>
              <div className="capability-row-name">
                <strong>{isZh ? trigger.name_zh : trigger.name_en}</strong>
                <code>{trigger.key}</code>
              </div>
              <span className="pill capability-default">
                {formatDefault(trigger.default)}
              </span>
            </header>
            <p>{isZh ? trigger.description_zh : trigger.description_en}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
