import type { Locale } from "../../lib/i18n";
import { GraphPanel } from "./GraphPanel";

type GraphTabProps = {
  runId: string;
  anchor: string;
  graphId: string | null | undefined;
  locale: Locale;
};

export function GraphTab({ runId, anchor, graphId, locale }: GraphTabProps) {
  return <GraphPanel runId={runId} anchor={anchor} graphId={graphId ?? null} locale={locale} />;
}
