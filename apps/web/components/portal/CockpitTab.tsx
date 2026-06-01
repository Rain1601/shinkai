import type { Locale } from "../../lib/i18n";
import { EventStream } from "./EventStream";
import { FrontierQueueCard } from "./FrontierQueueCard";
import { HypothesisCard } from "./HypothesisCard";
import { InjectPanel } from "./InjectPanel";
import { InjectionHistory } from "./InjectionHistory";

type RunEvent = {
  event_id?: string;
  type?: string;
  ts?: number;
  data?: Record<string, unknown>;
};

type CockpitTabProps = {
  runId: string;
  status: string;
  events: RunEvent[];
  locale: Locale;
  canControlRuns: boolean;
  lastSeen?: number;
  onInject: (note: string, intent: string) => Promise<void> | void;
  onResolveCheckpoint: (
    decision: "approve" | "reject" | "modify",
    note: string,
  ) => Promise<void> | void;
};

export function CockpitTab({
  runId,
  status,
  events,
  locale,
  canControlRuns,
  lastSeen = 0,
  onInject,
  onResolveCheckpoint,
}: CockpitTabProps) {
  return (
    <div className="cockpit-tab">
      <div className="cockpit-tab-left">
        <HypothesisCard runId={runId} locale={locale} refreshSignal={events.length} />
        <FrontierQueueCard events={events} locale={locale} />
      </div>
      <div className="cockpit-tab-right">
        <InjectPanel
          disabled={!canControlRuns}
          locale={locale}
          status={status}
          onInject={onInject}
          onResolveCheckpoint={onResolveCheckpoint}
        />
        <InjectionHistory events={events} locale={locale} />
        <EventStream events={events} locale={locale} lastSeen={lastSeen} />
      </div>
    </div>
  );
}
