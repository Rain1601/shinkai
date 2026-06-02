import type { Locale } from "../../lib/i18n";
import { formatNumber, localizeText } from "../../lib/i18n";

type RunEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

type FrontierItem = {
  frontier_id: string;
  name: string;
  source: string;
  priority: number;
  selection_score: number;
  status: "queued" | "running" | "completed" | "blocked" | "reprioritized";
};

type FrontierQueueCardProps = {
  events: RunEvent[];
  locale?: Locale;
};

const SOURCE_COLORS: Record<string, string> = {
  planner: "#58A0BC",
  deterministic_planner: "#58A0BC",
  reviewer: "#B5BAC0",
  human_injection: "#C46B62",
};

function sourceLabel(source: string, isZh: boolean): string {
  if (isZh) {
    if (source === "planner" || source === "deterministic_planner") return "规划器";
    if (source === "reviewer") return "复盘器";
    if (source === "human_injection") return "人工";
    return source;
  }
  return source;
}

function deriveFrontier(events: RunEvent[]): FrontierItem[] {
  const items = new Map<string, FrontierItem>();
  for (const event of events) {
    if (event.type === "plan" || event.type === "role_step_completed") {
      const queue = event.data?.frontier_queue ?? event.data?.queue;
      if (Array.isArray(queue)) {
        for (const raw of queue) {
          if (!raw || typeof raw !== "object") continue;
          const item = raw as Partial<FrontierItem>;
          if (!item.frontier_id) continue;
          items.set(item.frontier_id, {
            frontier_id: item.frontier_id,
            name: item.name ?? "",
            source: item.source ?? "planner",
            priority: typeof item.priority === "number" ? item.priority : 0,
            selection_score:
              typeof item.selection_score === "number" ? item.selection_score : 0,
            status: (item.status as FrontierItem["status"]) ?? "queued",
          });
        }
      }
    }
    if (event.type === "frontier_selected" && typeof event.data?.frontier_id === "string") {
      const existing = items.get(event.data.frontier_id);
      if (existing) existing.status = "running";
    }
    if (
      event.type === "supply_chain_layer_started" &&
      typeof event.data?.frontier_id === "string"
    ) {
      const existing = items.get(event.data.frontier_id as string);
      if (existing) existing.status = "running";
    }
    if (
      event.type === "frontier_expanded" &&
      typeof event.data?.frontier_id === "string"
    ) {
      const existing = items.get(event.data.frontier_id as string);
      if (existing && existing.status !== "completed") existing.status = "running";
    }
    if (event.type === "frontier_reprioritized" && typeof event.data?.frontier_id === "string") {
      const existing = items.get(event.data.frontier_id);
      if (existing) existing.status = "reprioritized";
    }
    if (event.type === "company_dossier_created" && typeof event.data?.loop_index === "number") {
      // Implicit completion when dossiers are emitted for a layer.
      for (const item of items.values()) {
        if (item.status === "running") {
          item.status = "completed";
        }
      }
    }
    if (
      event.type === "injection_acknowledged" &&
      typeof event.data?.frontier_id === "string"
    ) {
      const fid = event.data.frontier_id;
      if (!items.has(fid)) {
        items.set(fid, {
          frontier_id: fid,
          name: String(event.data.note ?? ""),
          source: "human_injection",
          priority: 0.85,
          selection_score: 0.85,
          status: "queued",
        });
      }
    }
  }
  return Array.from(items.values());
}

export function FrontierQueueCard({ events, locale = "zh" }: FrontierQueueCardProps) {
  const isZh = locale === "zh";
  const items = deriveFrontier(events);
  const queued = items
    .filter((item) => item.status === "queued" || item.status === "reprioritized")
    .sort((a, b) => b.selection_score - a.selection_score);
  const running = items.filter((item) => item.status === "running");
  const completed = items.filter((item) => item.status === "completed");

  function renderColumn(label: string, list: FrontierItem[]) {
    return (
      <div className="frontier-column">
        <div className="frontier-column-heading">
          <strong>{label}</strong>
          <span className="label">{list.length}</span>
        </div>
        <div className="frontier-column-items">
          {list.length === 0 ? (
            <p className="muted">{isZh ? "暂无" : "none"}</p>
          ) : null}
          {list.map((item) => (
            <article
              className="frontier-item"
              id={`frontier-${item.frontier_id}`}
              key={item.frontier_id}
              style={{ borderLeftColor: SOURCE_COLORS[item.source] ?? "#888" }}
            >
              <span className="frontier-item-name">{localizeText(item.name, locale)}</span>
              <span className="frontier-item-meta">
                <span>{sourceLabel(item.source, isZh)}</span>
                <span>{isZh ? "评分" : "score"} {formatNumber(item.selection_score)}</span>
              </span>
            </article>
          ))}
        </div>
      </div>
    );
  }

  return (
    <section className="surface frontier-queue-card">
      <div className="panel-heading">
        <h2>{isZh ? "前沿队列" : "Frontier Queue"}</h2>
        <span className="label">{items.length}</span>
      </div>
      <div className="frontier-columns">
        {renderColumn(isZh ? "排队中" : "Queued", queued)}
        {renderColumn(isZh ? "进行中" : "Running", running)}
        {renderColumn(isZh ? "已完成" : "Completed", completed)}
      </div>
    </section>
  );
}
