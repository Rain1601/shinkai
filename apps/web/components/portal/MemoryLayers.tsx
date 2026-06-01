"use client";

import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";

type Layer = {
  layer: string;
  name_en: string;
  name_zh: string;
  description_en: string;
  description_zh: string;
  count: number;
  sample: Array<Record<string, unknown>>;
  status: "live" | "scaffolded";
};

type MemoryLayersProps = {
  locale: Locale;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export function MemoryLayers({ locale }: MemoryLayersProps) {
  const isZh = locale === "zh";
  const [layers, setLayers] = useState<Layer[]>([]);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/actions/memory`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const data: Layer[] = await response.json();
        if (!cancelled) setLayers(data);
      } catch {
        // silent
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="surface memory-layers-panel">
      <div className="panel-heading">
        <h2>{isZh ? "记忆层级" : "Memory layers"}</h2>
        <span className="label">{layers.length}</span>
      </div>
      <div className="memory-layers-list">
        {layers.map((layer) => (
          <article
            className={`memory-layer-row memory-layer-${layer.status}`}
            key={layer.layer}
          >
            <header>
              <div>
                <strong>{isZh ? layer.name_zh : layer.name_en}</strong>
                <code>{layer.layer}</code>
              </div>
              <span className="pill">
                {layer.status === "live"
                  ? `${layer.count} ${isZh ? "条" : "items"}`
                  : isZh
                    ? "未启用 V1"
                    : "V1 — not live"}
              </span>
            </header>
            <p>{isZh ? layer.description_zh : layer.description_en}</p>
            {layer.sample && layer.sample.length > 0 ? (
              <ul className="memory-layer-sample">
                {layer.sample.map((item, index) => (
                  <li key={index}>
                    <code>
                      {(item.claim as string) ??
                        (item.note as string) ??
                        JSON.stringify(item)}
                    </code>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
